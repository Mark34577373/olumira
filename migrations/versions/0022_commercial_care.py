"""Additive care plans, reviewed handoff drafts and frozen optional step timers."""

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "care_plans",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("family_workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.String(32),
            sa.ForeignKey("care_profiles.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("priorities", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "updated_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','active','archived')", name="ck_care_plan_status"
        ),
    )
    op.create_index("ix_care_plans_scope", "care_plans", ["workspace_id", "profile_id"])
    op.create_table(
        "care_goals",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "plan_id",
            sa.String(32),
            sa.ForeignKey("care_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("target_date", sa.String(10)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned','in_progress','completed','paused')",
            name="ck_care_goal_status",
        ),
    )
    op.create_index("ix_care_goals_plan_id", "care_goals", ["plan_id"])
    for table, column, target, kind in [
        ("care_plan_routines", "routine_id", "routines.id", sa.Integer()),
        ("care_plan_boards", "board_id", "communication_boards.id", sa.String(32)),
        ("care_plan_tasks", "task_id", "caregiver_tasks.id", sa.String(32)),
    ]:
        op.create_table(
            table,
            sa.Column(
                "plan_id",
                sa.String(32),
                sa.ForeignKey("care_plans.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(column, kind, sa.ForeignKey(target), primary_key=True),
        )
    op.create_table(
        "handoff_drafts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("family_workspaces.id"),
            nullable=False,
        ),
        sa.Column("profile_id", sa.String(32), sa.ForeignKey("care_profiles.id")),
        sa.Column(
            "created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "recipient_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("summary", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shared_id", sa.String(32), sa.ForeignKey("caregiver_handoffs.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','ready','shared')", name="ck_handoff_draft_status"
        ),
    )
    op.create_index(
        "ix_handoff_drafts_scope",
        "handoff_drafts",
        ["workspace_id", "profile_id", "created_by"],
    )
    for table in ("routine_steps", "routine_session_steps"):
        op.add_column(
            table,
            sa.Column(
                "timer_seconds", sa.Integer(), nullable=False, server_default="0"
            ),
        )


def downgrade():
    raise RuntimeError(
        "Review retained care plans and handoff history before downgrade."
    )
