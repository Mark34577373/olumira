"""Private family workspaces; preserve all legacy records and identifiers."""

from alembic import op
import sqlalchemy as sa
import uuid
from datetime import datetime, timezone

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "family_workspaces",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column(
            "created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("family_workspaces.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
        sa.CheckConstraint(
            "role IN ('owner','caregiver','viewer')", name="ck_membership_role"
        ),
        sa.CheckConstraint(
            "status IN ('active','revoked')", name="ck_membership_status"
        ),
    )
    for column in ("workspace_id", "user_id"):
        op.create_index(
            "ix_workspace_memberships_" + column, "workspace_memberships", [column]
        )
    connection = op.get_bind()
    # INSERT SELECT works online and in reviewed offline PostgreSQL SQL scripts.
    op.execute(
        "INSERT INTO family_workspaces (id,name,created_by,created_at,updated_at) SELECT owner_id,'Our Family',id,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM users"
    )
    op.execute(
        "INSERT INTO workspace_memberships (id,workspace_id,user_id,role,status,joined_at) SELECT id,owner_id,id,'owner','active',CURRENT_TIMESTAMP FROM users"
    )
    for table in ("routines", "observations"):
        # Nullable ownership preserves unclaimed legacy data; no table rebuild needed.
        if connection.dialect.name == "sqlite":
            op.execute(
                sa.text(
                    "ALTER TABLE "
                    + table
                    + " ADD COLUMN workspace_id VARCHAR(32) REFERENCES family_workspaces(id)"
                )
            )
        else:
            op.add_column(
                table,
                sa.Column(
                    "workspace_id",
                    sa.String(32),
                    sa.ForeignKey(
                        "family_workspaces.id", name="fk_" + table + "_workspace"
                    ),
                    nullable=True,
                ),
            )
        op.create_index("ix_" + table + "_workspace_id", table, ["workspace_id"])
        connection.execute(
            sa.text(
                "UPDATE "
                + table
                + " SET workspace_id=owner_id WHERE owner_id IN (SELECT owner_id FROM users)"
            )
        )


def downgrade():
    raise RuntimeError(
        "Use a reviewed backup restore; workspace data must not be deleted automatically."
    )
