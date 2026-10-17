"""Add single-use account tokens, credential generations, and encrypted email queue.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('pending_email', sa.String(254)))
    op.add_column('users', sa.Column('auth_version', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('auth_sessions', sa.Column('auth_version', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('account_tokens',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purpose', sa.String(24), nullable=False), sa.Column('target_email', sa.String(254), nullable=False),
        sa.Column('auth_version', sa.Integer(), nullable=False), sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('expires_at', sa.BigInteger(), nullable=False), sa.Column('used_at', sa.BigInteger()),
        sa.CheckConstraint("purpose IN ('verify_email', 'reset_password', 'change_email')", name='ck_account_tokens_purpose'))
    op.create_index('ix_account_tokens_user_id', 'account_tokens', ['user_id'])
    op.create_table('email_outbox',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), sa.ForeignKey('account_tokens.token_hash', ondelete='CASCADE')),
        sa.Column('kind', sa.String(24), nullable=False), sa.Column('encrypted_payload', sa.Text(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False), sa.Column('expires_at', sa.BigInteger(), nullable=False),
        sa.Column('available_at', sa.BigInteger(), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('delivered_at', sa.BigInteger()), sa.Column('cancelled_at', sa.BigInteger()),
        sa.Column('last_error', sa.String(32)))
    op.create_index('ix_email_outbox_available_at', 'email_outbox', ['available_at'])


def downgrade():
    raise RuntimeError('Removing account recovery data requires an approved recovery plan.')
