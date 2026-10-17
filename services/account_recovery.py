"""Single-use, purpose-bound account links and reauthenticated settings changes."""
import re
import secrets
import time
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from email_validator import EmailNotValidError
from flask import current_app
from olumira.extensions import db
from olumira.models import User, AuthSession, AccountToken, EmailOutbox
from services.authentication import normalize_email, token_digest, password_error, PASSWORD_METHOD
from services.database import transaction
from services.email_delivery import queue_email, cipher


def _user(user_id):
    return db.session.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))


def _invalidate(user, purpose=None):
    moment = int(time.time())
    tokens = select(AccountToken.token_hash).where(AccountToken.user_id == user.id)
    if purpose:
        tokens = tokens.where(AccountToken.purpose == purpose)
    db.session.execute(update(EmailOutbox).where(EmailOutbox.token_hash.in_(tokens),
                       EmailOutbox.delivered_at.is_(None)).values(cancelled_at=moment))
    db.session.execute(update(AccountToken).where(AccountToken.token_hash.in_(tokens),
                       AccountToken.used_at.is_(None)).values(used_at=moment))


def _issue(user, purpose, target):
    _invalidate(user, purpose)
    raw, moment = secrets.token_urlsafe(32), int(time.time())
    ttl = current_app.config[{'verify_email': 'VERIFY_TOKEN_SECONDS', 'reset_password': 'RESET_TOKEN_SECONDS',
                             'change_email': 'EMAIL_CHANGE_TOKEN_SECONDS'}[purpose]]
    record = AccountToken(token_hash=token_digest(raw), user_id=user.id, purpose=purpose, target_email=target,
                          auth_version=user.auth_version, created_at=moment, expires_at=moment + ttl)
    db.session.add(record)
    db.session.flush()
    queue_email(user, purpose, target, token=(raw, record.token_hash), expires_at=record.expires_at)


def _cover_work():
    # Do not connect to SMTP, even for known accounts; unknown requests do local cryptographic work too.
    cipher().encrypt(secrets.token_bytes(256))


def request_link(email, purpose):
    if purpose not in {'verify_email', 'reset_password'}:
        raise ValueError('Unsupported public account-link purpose')
    try:
        normalized = normalize_email(email)
    except EmailNotValidError:
        normalized = ''
    with transaction():
        user_id = db.session.scalar(select(User.id).where(User.email == normalized))
        user = _user(user_id) if user_id else None
        if user and user.closed_at is None and (purpose != 'verify_email' or not user.email_verified):
            _issue(user, purpose, user.email)
        else:
            _cover_work()
    # No existence or delivery result is exposed to the caller.


def _lookup(raw, purpose, lock=False):
    if not isinstance(raw, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', raw):
        return None
    query = select(AccountToken).where(AccountToken.token_hash == token_digest(raw), AccountToken.purpose == purpose)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.session.scalar(query)


def _valid_token(raw, purpose):
    initial = _lookup(raw, purpose)
    if not initial:
        return None, None
    user = _user(initial.user_id)
    token = _lookup(raw, purpose, lock=True)
    if (not user or user.closed_at is not None or not token or token.used_at is not None or token.expires_at <= int(time.time()) or
            token.auth_version != user.auth_version):
        return None, None
    return user, token


def _claim(token):
    moment = int(time.time())
    return db.session.execute(update(AccountToken).where(
        AccountToken.token_hash == token.token_hash, AccountToken.used_at.is_(None),
        AccountToken.expires_at > moment).values(used_at=moment)).rowcount == 1


def _revoke(user):
    user.auth_version += 1
    user.pending_email = None
    _invalidate(user)
    db.session.execute(update(AuthSession).where(AuthSession.user_id == user.id,
                       AuthSession.revoked_at.is_(None)).values(revoked_at=int(time.time())))


def verify_email(raw):
    with transaction():
        user, token = _valid_token(raw, 'verify_email')
        if not user or user.email_verified or token.target_email != user.email or not _claim(token):
            return None
        user.email_verified = True
        _revoke(user)
        return user.id


def reset_password(raw, password):
    if password_error(password):
        return None
    with transaction():
        user, token = _valid_token(raw, 'reset_password')
        if not user or token.target_email != user.email:
            return None
        new_hash = generate_password_hash(password, method=PASSWORD_METHOD)
        if not _claim(token):
            return None
        user.password_hash = new_hash
        _revoke(user)
        queue_email(user, 'password_changed', user.email)
        return user.id


def update_profile(user_id, display_name):
    name = (display_name or '').strip()
    if not 1 <= len(name) <= 80:
        return False
    with transaction():
        user = _user(user_id)
        if not user:
            return False
        user.display_name = name
    return True


def _reauthenticated(user, password):
    return user is not None and isinstance(password, str) and len(password) <= 128 and check_password_hash(user.password_hash, password)


def change_password(user_id, current_password, new_password):
    if password_error(new_password):
        return False
    with transaction():
        user = _user(user_id)
        if not _reauthenticated(user, current_password):
            return False
        user.password_hash = generate_password_hash(new_password, method=PASSWORD_METHOD)
        _revoke(user)
        queue_email(user, 'password_changed', user.email)
    return True


def request_email_change(user_id, current_password, email):
    try:
        normalized = normalize_email(email)
    except EmailNotValidError:
        return False
    with transaction():
        user = _user(user_id)
        if not _reauthenticated(user, current_password) or normalized == user.email:
            return False
        if db.session.scalar(select(User.id).where(User.email == normalized)) is not None:
            return False
        user.pending_email = normalized
        _issue(user, 'change_email', normalized)
    return True


def confirm_email_change(raw):
    try:
        with transaction():
            user, token = _valid_token(raw, 'change_email')
            if not user or not user.pending_email or token.target_email != user.pending_email:
                return None
            if db.session.scalar(select(User.id).where(User.email == token.target_email, User.id != user.id)):
                return None
            old_email, was_verified, new_email = user.email, user.email_verified, token.target_email
            if not _claim(token):
                return None
            user.email, user.email_verified = new_email, True
            _revoke(user)
            if was_verified:
                queue_email(user, 'email_changed', old_email, new_email=new_email)
            queue_email(user, 'email_changed', new_email, new_email=new_email)
            return user.id
    except IntegrityError:
        # A concurrently confirmed address remains protected by database uniqueness.
        return None


def cancel_email_change(user_id, current_password):
    with transaction():
        user = _user(user_id)
        if not _reauthenticated(user, current_password):
            return False
        user.pending_email = None
        _invalidate(user, 'change_email')
    return True


def sign_out_everywhere(user_id, current_password):
    with transaction():
        user = _user(user_id)
        if not _reauthenticated(user, current_password):
            return False
        _revoke(user)
    return True
