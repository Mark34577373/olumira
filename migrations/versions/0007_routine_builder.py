"""Add routine templates and steps without rebuilding or deleting legacy parents."""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("icon", sa.String(24), nullable=False, server_default="sun"),
        sa.Column("color", sa.String(16), nullable=False, server_default="sage"),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_checklist", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    ]:
        op.add_column("routines", column)
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE routines ADD COLUMN created_by VARCHAR(32) REFERENCES users(id)"
        )
    else:
        op.add_column(
            "routines",
            sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id")),
        )
    op.create_table(
        "routine_steps",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "routine_id",
            sa.Integer,
            sa.ForeignKey("routines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("icon", sa.String(24), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("routine_id", "position", name="uq_routine_step_position"),
        sa.CheckConstraint("position >= 0", name="ck_routine_step_position"),
    )
    op.create_index("ix_routine_steps_routine_id", "routine_steps", ["routine_id"])
    # Stable text IDs work in online and offline SQL; old routine IDs remain unchanged.
    op.execute(
        "INSERT INTO routine_steps (id,routine_id,title,description,icon,position,created_at,updated_at) SELECT 'legacy-' || CAST(id AS VARCHAR),id,name,'','sun',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM routines"
    )
    op.create_table(
        "routine_completion_snapshots",
        sa.Column("routine_id", sa.Integer, primary_key=True),
        sa.Column("completion_date", sa.Text, primary_key=True),
        sa.Column("workspace_id", sa.String(32), sa.ForeignKey("family_workspaces.id")),
        sa.Column("profile_id", sa.String(32), sa.ForeignKey("care_profiles.id")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["routine_id", "completion_date"],
            ["routine_completions.routine_id", "routine_completions.completion_date"],
            ondelete="CASCADE",
        ),
    )
    op.execute(
        "INSERT INTO routine_completion_snapshots (routine_id,completion_date,workspace_id,profile_id,name,category,source,captured_at) SELECT c.routine_id,c.completion_date,r.workspace_id,r.profile_id,r.name,r.category,'migration',CURRENT_TIMESTAMP FROM routine_completions c JOIN routines r ON r.id=c.routine_id"
    )


def downgrade():
    raise RuntimeError(
        "Routine history must not be automatically discarded; use reviewed backup recovery."
    )
