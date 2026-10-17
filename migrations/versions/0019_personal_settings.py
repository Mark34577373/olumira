"""Persistent personal display preferences; no shared data changes."""

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "user_preferences",
        sa.Column(
            "user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        *[
            sa.Column(name, sa.Boolean(), nullable=False)
            for name in [
                "larger_text",
                "reduced_motion",
                "enhanced_contrast",
                "simplified",
                "reduced_effects",
            ]
        ],
        sa.Column("calendar_view", sa.String(10), nullable=False),
        sa.Column("week_start", sa.String(6), nullable=False),
        sa.Column("time_format", sa.String(2), nullable=False),
        sa.CheckConstraint("calendar_view IN ('month','week','day','agenda')"),
        sa.CheckConstraint("week_start IN ('monday','sunday')"),
        sa.CheckConstraint("time_format IN ('12','24')")
    )


def downgrade():
    raise RuntimeError("Review and back up personal preferences before downgrade.")
