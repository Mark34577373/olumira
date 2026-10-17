"""Models mirror the legacy schema, including nullable legacy ownership."""
from .extensions import db


class Owner(db.Model):
    __tablename__ = 'owners'
    id = db.Column(db.Text, primary_key=True)
    created_at = db.Column(db.Text, nullable=False)


class Routine(db.Model):
    __tablename__ = 'routines'
    __table_args__ = (db.Index('idx_routines_owner', 'owner_id'), {'sqlite_autoincrement': True})
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Text, nullable=True)
    name = db.Column(db.Text, nullable=False)
    category = db.Column(db.Text, nullable=False)


class Observation(db.Model):
    __tablename__ = 'observations'
    __table_args__ = (db.Index('idx_observations_owner', 'owner_id'), {'sqlite_autoincrement': True})
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Text, nullable=True)
    activity = db.Column(db.Text, nullable=False)
    date = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    mood = db.Column(db.Text)
    tags = db.Column(db.Text)


class RoutineCompletion(db.Model):
    __tablename__ = 'routine_completions'
    routine_id = db.Column(db.Integer, db.ForeignKey('routines.id', ondelete='CASCADE'), primary_key=True)
    completion_date = db.Column(db.Text, primary_key=True)


from datetime import datetime, timezone
from flask_login import UserMixin


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    __table_args__ = (
        db.UniqueConstraint('email', name='uq_users_email'),
        db.UniqueConstraint('owner_id', name='uq_users_owner'),
        db.CheckConstraint('email = lower(email)', name='ck_users_email_normalized'),
    )
    id = db.Column(db.String(32), primary_key=True)
    email = db.Column(db.String(254), nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    pending_email = db.Column(db.String(254))
    auth_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    # Only explicitly linked account owners are accessible; legacy owners stay unlinked.
    owner_id = db.Column(db.Text, db.ForeignKey('owners.id'), nullable=False)


class AuthSession(db.Model):
    __tablename__ = 'auth_sessions'
    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.BigInteger, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    last_seen_at = db.Column(db.BigInteger, nullable=False)
    revoked_at = db.Column(db.BigInteger)
    auth_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')


class AccountToken(db.Model):
    __tablename__ = 'account_tokens'
    __table_args__ = (db.CheckConstraint("purpose IN ('verify_email', 'reset_password', 'change_email')", name='ck_account_tokens_purpose'),)
    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    purpose = db.Column(db.String(24), nullable=False)
    target_email = db.Column(db.String(254), nullable=False)
    auth_version = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.BigInteger, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    used_at = db.Column(db.BigInteger)


class EmailOutbox(db.Model):
    __tablename__ = 'email_outbox'
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token_hash = db.Column(db.String(64), db.ForeignKey('account_tokens.token_hash', ondelete='CASCADE'))
    kind = db.Column(db.String(24), nullable=False)
    encrypted_payload = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.BigInteger, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    available_at = db.Column(db.BigInteger, nullable=False, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    delivered_at = db.Column(db.BigInteger)
    cancelled_at = db.Column(db.BigInteger)
    last_error = db.Column(db.String(32))
