"""Extend the original journal without inventing legacy authors or event times."""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    timestamp = "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"
    for name, definition in [
        ("category", "VARCHAR(60) NOT NULL DEFAULT 'General notes'"),
        ("author_id", "VARCHAR(32) REFERENCES users(id)"),
        ("observed_at", timestamp),
        ("timezone", "VARCHAR(64)"),
        ("created_at", timestamp),
        ("updated_at", timestamp),
        ("archived_at", timestamp),
        ("version", "INTEGER NOT NULL DEFAULT 1"),
        ("session_id", "VARCHAR(32) REFERENCES routine_sessions(id)"),
        ("task_id", "VARCHAR(32) REFERENCES caregiver_tasks(id)"),
    ]:
        op.execute(f"ALTER TABLE observations ADD COLUMN {name} {definition}")
    op.create_index(
        "ix_observations_scope_time",
        "observations",
        ["workspace_id", "profile_id", "observed_at", "id"],
    )
    op.create_index(
        "ix_observations_scope_category",
        "observations",
        ["workspace_id", "profile_id", "category"],
    )
    op.create_index(
        "ix_sessions_scope_completed",
        "routine_sessions",
        ["workspace_id", "profile_id", "completed_at"],
    )
    op.create_index(
        "ix_tasks_scope_completed",
        "caregiver_tasks",
        ["workspace_id", "profile_id", "completed_at"],
    )
    # Validate linked frozen sessions/tasks against the observation's exact scope.
    predicate = "(NEW.session_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routine_sessions s WHERE s.id=NEW.session_id AND s.workspace_id=NEW.workspace_id AND {profile})) OR (NEW.task_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM caregiver_tasks s WHERE s.id=NEW.task_id AND s.workspace_id=NEW.workspace_id AND {profile}))"
    if dialect == "sqlite":
        predicate = predicate.format(profile="s.profile_id IS NEW.profile_id")
        op.execute(
            "CREATE TRIGGER observations_provenance BEFORE UPDATE ON observations WHEN NEW.workspace_id IS NOT OLD.workspace_id OR NEW.profile_id IS NOT OLD.profile_id OR NEW.author_id IS NOT OLD.author_id OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT, 'Observation provenance is immutable'); END"
        )
        for action in ["INSERT", "UPDATE"]:
            op.execute(
                f"CREATE TRIGGER observations_links_{action.lower()} BEFORE {action} ON observations WHEN {predicate} BEGIN SELECT RAISE(ABORT, 'Observation reference scope mismatch'); END"
            )
    elif dialect == "postgresql":
        predicate = predicate.format(
            profile="s.profile_id IS NOT DISTINCT FROM NEW.profile_id"
        )
        op.execute(
            "CREATE FUNCTION preserve_observation_provenance() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR NEW.profile_id IS DISTINCT FROM OLD.profile_id OR NEW.author_id IS DISTINCT FROM OLD.author_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN RAISE EXCEPTION 'Observation provenance is immutable'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER observations_provenance BEFORE UPDATE ON observations FOR EACH ROW EXECUTE FUNCTION preserve_observation_provenance()"
        )
        op.execute(
            f"CREATE FUNCTION check_observation_links() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF {predicate} THEN RAISE EXCEPTION 'Observation reference scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER observations_links BEFORE INSERT OR UPDATE ON observations FOR EACH ROW EXECUTE FUNCTION check_observation_links()"
        )


def downgrade():
    raise RuntimeError("Review and back up observation metadata before downgrading.")
