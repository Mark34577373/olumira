"""Add account ownership and revocable sessions without changing legacy records.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('display_name', sa.String(80), nullable=False),
        sa.Column('email_verified', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('owner_id', sa.Text(), sa.ForeignKey('owners.id'), nullable=False),
        sa.UniqueConstraint('email', name='uq_users_email'),
        sa.UniqueConstraint('owner_id', name='uq_users_owner'),
        sa.CheckConstraint('email = lower(email)', name='ck_users_email_normalized'))
    op.create_table('auth_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('expires_at', sa.BigInteger(), nullable=False),
        sa.Column('last_seen_at', sa.BigInteger(), nullable=False),
        sa.Column('revoked_at', sa.BigInteger()))
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])


def downgrade():
    raise RuntimeError('Removing accounts is destructive. Use an approved backup/recovery plan instead.')
