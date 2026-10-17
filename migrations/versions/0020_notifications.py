"""Durable in-app notifications and member-owned notification preferences."""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("family_workspaces.id"),
            nullable=False,
        ),
        sa.Column("profile_id", sa.String(32), sa.ForeignKey("care_profiles.id")),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("dedup_key", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["profile_id", "workspace_id"],
            ["care_profiles.id", "care_profiles.workspace_id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspace_memberships.workspace_id", "workspace_memberships.user_id"],
        ),
        sa.CheckConstraint("category IN ('task','handoff','routine','event')"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_workspace_id", "notifications", ["workspace_id"])
    op.create_index(
        "ix_notification_inbox",
        "notifications",
        ["user_id", "workspace_id", "dismissed_at", "read_at", "created_at"],
    )
    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True
        ),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("family_workspaces.id"),
            primary_key=True,
        ),
        sa.Column("categories", sa.String(100), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("retention_days IN (30,90,180)"),
    )


def downgrade():
    raise RuntimeError("Review notification history before downgrade.")
