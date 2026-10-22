"""Account creation, password checks and revocable authentication sessions."""
import hashlib
import secrets
import time
import uuid
from functools import lru_cache
from email_validator import validate_email, EmailNotValidError
from flask import current_app, g, session
from flask_login import login_user, logout_user
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from olumira.extensions import db
from olumira.models import User, Owner, Routine, RoutineStep, AuthSession
from services.database import STARTER_ROUTINES, today_string, transaction

PASSWORD_METHOD = 'scrypt:131072:8:1'
# An offline guard against a few widely known choices, not a breach-corpus check.
COMMON_PASSWORDS = frozenset({'passwordpassword', 'password123456789', '123456789012345',
                            'qwertyuiopasdfgh', 'correct horse battery staple'})


def normalize_email(value: str) -> str:
    return validate_email((value or '').strip(), check_deliverability=False,
                          allow_smtputf8=False).ascii_email.casefold()


def password_error(value: str):
    if not 15 <= len(value) <= 128:
        return 'Use 15–128 characters. A long, unique passphrase works well.'
    if value.casefold() in COMMON_PASSWORDS:
        return 'Choose a less common password or a unique passphrase.'
    return None


@lru_cache(maxsize=1)
def dummy_password_hash():
    return generate_password_hash(secrets.token_urlsafe(32), method=PASSWORD_METHOD)


def register_user(email: str, display_name: str, password: str):
    email = normalize_email(email)
    display_name = (display_name or '').strip()
    if not 1 <= len(display_name) <= 80 or password_error(password):
        raise ValueError('Invalid registration values')
    # Hash valid registration attempts before the duplicate check so an existing
    # address does not take a cheap password-work bypass. No constant-time claim.
    password_hash = generate_password_hash(password, method=PASSWORD_METHOD)
    if db.session.scalar(select(User.id).where(User.email == email)) is not None:
        return None
    owner_id, user_id = uuid.uuid4().hex, uuid.uuid4().hex
    try:
        with transaction() as store:
            store.add(Owner(id=owner_id, created_at=today_string()))
            store.flush()
            user = User(id=user_id, owner_id=owner_id, email=email, display_name=display_name,
                        password_hash=password_hash, email_verified=False)
            store.add(user)
            store.flush()
            from services.workspaces import create_workspace
            create_workspace(user_id, 'Our Family', workspace_id=owner_id)
            for name, category in STARTER_ROUTINES:
                routine=Routine(owner_id=owner_id,workspace_id=owner_id,name=name,category=category)
                store.add(routine);store.flush()
                store.add(RoutineStep(id=uuid.uuid4().hex,routine_id=routine.id,title=name,description='',icon='sun',position=0))
            store.flush()
        return user
    except IntegrityError:
        # The unique constraint also handles simultaneous duplicate registrations.
        if db.session.scalar(select(User.id).where(User.email == email)) is not None:
            return None
        raise


def authenticate(email: str, password: str):
    try:
        normalized = normalize_email(email)
    except EmailNotValidError:
        normalized = ''
    user = db.session.scalar(select(User).where(User.email == normalized))
    usable_password = isinstance(password, str) and len(password) <= 128
    candidate = password if usable_password else ''
    checked_version = user.auth_version if user else None
    valid = check_password_hash(user.password_hash if user else dummy_password_hash(), candidate)
    if not user or user.closed_at is not None or not valid or not usable_password:
        return None
    if user.password_hash.split('$', 1)[0] != PASSWORD_METHOD:
        with transaction() as store:
            user = store.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
            if user.auth_version != checked_version:
                return None
            user.password_hash = generate_password_hash(password, method=PASSWORD_METHOD)
    user._authenticated_version = checked_version
    return user


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def revoke_current_session():
    token = session.get('_auth_sid')
    if isinstance(token, str) and token.isascii() and len(token) <= 128:
        with transaction() as store:
            store.execute(update(AuthSession).where(AuthSession.token_hash == token_digest(token),
                                                    AuthSession.revoked_at.is_(None)).values(revoked_at=int(time.time())))


def start_session(user):
    # Capture the credential generation checked by authenticate(), before refreshing the row.
    expected_version = getattr(user, '_authenticated_version', None)
    user_id = user.id
    revoke_current_session()
    logout_user()
    session.clear()
    token, issued = secrets.token_urlsafe(32), int(time.time())
    with transaction() as store:
        user = store.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
        if user is None or user.closed_at is not None or expected_version is None or user.auth_version != expected_version:
            return False
        store.add(AuthSession(token_hash=token_digest(token), user_id=user.id, auth_version=user.auth_version,
                              created_at=issued, expires_at=issued + current_app.config['AUTH_SESSION_SECONDS'], last_seen_at=issued))
    login_user(user, remember=False, fresh=True)
    session['_auth_sid'] = token
    session.permanent = True
    return True


def end_session():
    revoke_current_session()
    logout_user()
    session.clear()


def load_user(user_id):
    token = session.get('_auth_sid')
    if not isinstance(token, str) or not token.isascii() or not 32 <= len(token) <= 128:
        g.auth_expired = True
        session.clear()
        return None
    record = db.session.get(AuthSession, token_digest(token))
    moment = int(time.time())
    if (record is None or record.user_id != user_id or record.revoked_at is not None or
            record.expires_at <= moment or record.last_seen_at + current_app.config['AUTH_IDLE_SECONDS'] <= moment):
        g.auth_expired = True
        if record and record.user_id == user_id and record.revoked_at is None:
            with transaction():
                record.revoked_at = moment
        session.clear()
        return None
    user = db.session.get(User, user_id)
    if user is None or user.closed_at is not None or user.auth_version != record.auth_version:
        g.auth_expired = True
        session.clear()
        return None
    if moment - record.last_seen_at >= 60:
        with transaction():
            record.last_seen_at = moment
    return user


def revoke_all_sessions(user_id: str):
    """Revoke stored handles. Credential changes use account_recovery to advance auth_version too."""
    with transaction() as store:
        store.execute(update(AuthSession).where(AuthSession.user_id == user_id,
                                               AuthSession.revoked_at.is_(None)).values(revoked_at=int(time.time())))
