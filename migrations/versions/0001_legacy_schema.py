"""Baseline of the existing schema, preserving legacy nullable owners and text dates.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('owners', sa.Column('id', sa.Text(), primary_key=True), sa.Column('created_at', sa.Text(), nullable=False))
    op.create_table('routines', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('owner_id', sa.Text()), sa.Column('name', sa.Text(), nullable=False), sa.Column('category', sa.Text(), nullable=False), sqlite_autoincrement=True)
    op.create_index('idx_routines_owner', 'routines', ['owner_id'])
    op.create_table('observations', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('owner_id', sa.Text()), sa.Column('activity', sa.Text(), nullable=False), sa.Column('date', sa.Text(), nullable=False), sa.Column('notes', sa.Text()), sa.Column('mood', sa.Text()), sa.Column('tags', sa.Text()), sqlite_autoincrement=True)
    op.create_index('idx_observations_owner', 'observations', ['owner_id'])
    op.create_table('routine_completions', sa.Column('routine_id', sa.Integer(), sa.ForeignKey('routines.id', ondelete='CASCADE'), primary_key=True), sa.Column('completion_date', sa.Text(), primary_key=True))


def downgrade():
    # Recovery uses a verified backup rather than a destructive schema reset.
    raise RuntimeError('Baseline downgrade is destructive. Restore a verified backup instead.')
