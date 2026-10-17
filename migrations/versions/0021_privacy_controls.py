"""Private download grants and auditable access closure, preserving shared history."""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("closed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "family_workspaces", sa.Column("closed_at", sa.DateTime(timezone=True))
    )
    op.create_table(
        "data_exports",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", sa.String(32), sa.ForeignKey("family_workspaces.id")),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("consumed_at", sa.BigInteger()),
        sa.CheckConstraint("scope IN ('personal','workspace')"),
    )
    op.create_index("ix_data_exports_user_id", "data_exports", ["user_id"])
    op.create_index("ix_data_exports_expires_at", "data_exports", ["expires_at"])
    op.create_table(
        "deletion_requests",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", sa.String(32), sa.ForeignKey("family_workspaces.id")),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    raise RuntimeError("Access-closure records must be reviewed before downgrade.")
