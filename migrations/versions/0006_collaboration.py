"""Caregiver invitations and append-only application audit events."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("family_workspaces.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "invited_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("expires_at", sa.BigInteger, nullable=False),
        sa.Column("accepted_at", sa.BigInteger),
        sa.Column("revoked_at", sa.BigInteger),
        sa.CheckConstraint("role IN ('caregiver','viewer')", name="ck_invitation_role"),
    )
    op.create_index(
        "ix_workspace_invitations_workspace_id",
        "workspace_invitations",
        ["workspace_id"],
    )
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE email_outbox ADD COLUMN invitation_id VARCHAR(32) REFERENCES workspace_invitations(id)"
        )
    else:
        op.add_column(
            "email_outbox",
            sa.Column(
                "invitation_id",
                sa.String(32),
                sa.ForeignKey("workspace_invitations.id"),
            ),
        )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("family_workspaces.id"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("target_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_workspace_id", "audit_events", ["workspace_id"])
    # Application exposes no edit/delete path; DB rejects accidental mutation as well.
    if op.get_bind().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(
                sa.text(
                    "CREATE TRIGGER audit_events_no_"
                    + action.lower()
                    + " BEFORE "
                    + action
                    + " ON audit_events BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END"
                )
            )
    else:
        op.execute(
            "CREATE FUNCTION olumira_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit events are append-only'; END $$"
        )
        op.execute(
            "CREATE TRIGGER audit_events_immutable BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION olumira_audit_immutable()"
        )


def downgrade():
    raise RuntimeError(
        "Audit history and invitations must not be automatically deleted."
    )
