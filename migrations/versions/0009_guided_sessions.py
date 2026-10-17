"""Additive routine guided sessions tables; no legacy rewrites."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "CREATE TABLE routine_sessions (\n\tid VARCHAR(32) NOT NULL, \n\troutine_id INTEGER NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\toccurrence_id VARCHAR(64), \n\tactive_key VARCHAR(64), \n\ttitle TEXT NOT NULL, \n\tdescription TEXT NOT NULL, \n\ticon VARCHAR(24) NOT NULL, \n\tcolor VARCHAR(16) NOT NULL, \n\tprofile_name VARCHAR(80) NOT NULL, \n\troutine_version INTEGER NOT NULL, \n\tstatus VARCHAR(12) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tstarted_by VARCHAR(32) NOT NULL, \n\tstarted_at DATETIME NOT NULL, \n\tpaused_at DATETIME, \n\tcompleted_at DATETIME, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_session_status CHECK (status IN ('active','paused','completed')), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tUNIQUE (occurrence_id), \n\tFOREIGN KEY(occurrence_id) REFERENCES routine_occurrences (id), \n\tUNIQUE (active_key), \n\tFOREIGN KEY(started_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_sessions_routine_id ON routine_sessions (routine_id)"
        )
        op.execute(
            "CREATE INDEX ix_sessions_scope_started ON routine_sessions (workspace_id, profile_id, started_at)"
        )
        op.execute(
            "CREATE TABLE routine_session_steps (\n\tid VARCHAR(32) NOT NULL, \n\tsession_id VARCHAR(32) NOT NULL, \n\ttitle TEXT NOT NULL, \n\tdescription VARCHAR(500) NOT NULL, \n\ticon VARCHAR(24) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tcompleted_by VARCHAR(32), \n\tcompleted_at DATETIME, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_session_step_position UNIQUE (session_id, position), \n\tCONSTRAINT ck_session_step_position CHECK (position >= 0), \n\tFOREIGN KEY(session_id) REFERENCES routine_sessions (id), \n\tFOREIGN KEY(completed_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_session_steps_session_id ON routine_session_steps (session_id)"
        )
        op.execute(
            "CREATE TABLE routine_session_events (\n\tid VARCHAR(32) NOT NULL, \n\tsession_id VARCHAR(32) NOT NULL, \n\tstep_id VARCHAR(32), \n\tactor_id VARCHAR(32) NOT NULL, \n\taction VARCHAR(24) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(session_id) REFERENCES routine_sessions (id), \n\tFOREIGN KEY(step_id) REFERENCES routine_session_steps (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_session_events_session_id ON routine_session_events (session_id)"
        )
        op.execute(
            "CREATE TABLE routine_launch_requests (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tactor_id VARCHAR(32) NOT NULL, \n\troutine_id INTEGER NOT NULL, \n\tsession_id VARCHAR(32) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(session_id) REFERENCES routine_sessions (id)\n)"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE TABLE routine_sessions (\n\tid VARCHAR(32) NOT NULL, \n\troutine_id INTEGER NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\toccurrence_id VARCHAR(64), \n\tactive_key VARCHAR(64), \n\ttitle TEXT NOT NULL, \n\tdescription TEXT NOT NULL, \n\ticon VARCHAR(24) NOT NULL, \n\tcolor VARCHAR(16) NOT NULL, \n\tprofile_name VARCHAR(80) NOT NULL, \n\troutine_version INTEGER NOT NULL, \n\tstatus VARCHAR(12) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tstarted_by VARCHAR(32) NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tpaused_at TIMESTAMP WITH TIME ZONE, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_session_status CHECK (status IN ('active','paused','completed')), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tUNIQUE (occurrence_id), \n\tFOREIGN KEY(occurrence_id) REFERENCES routine_occurrences (id), \n\tUNIQUE (active_key), \n\tFOREIGN KEY(started_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_sessions_routine_id ON routine_sessions (routine_id)"
        )
        op.execute(
            "CREATE INDEX ix_sessions_scope_started ON routine_sessions (workspace_id, profile_id, started_at)"
        )
        op.execute(
            "CREATE TABLE routine_session_steps (\n\tid VARCHAR(32) NOT NULL, \n\tsession_id VARCHAR(32) NOT NULL, \n\ttitle TEXT NOT NULL, \n\tdescription VARCHAR(500) NOT NULL, \n\ticon VARCHAR(24) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tcompleted_by VARCHAR(32), \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_session_step_position UNIQUE (session_id, position), \n\tCONSTRAINT ck_session_step_position CHECK (position >= 0), \n\tFOREIGN KEY(session_id) REFERENCES routine_sessions (id), \n\tFOREIGN KEY(completed_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_session_steps_session_id ON routine_session_steps (session_id)"
        )
        op.execute(
            "CREATE TABLE routine_session_events (\n\tid VARCHAR(32) NOT NULL, \n\tsession_id VARCHAR(32) NOT NULL, \n\tstep_id VARCHAR(32), \n\tactor_id VARCHAR(32) NOT NULL, \n\taction VARCHAR(24) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(session_id) REFERENCES routine_sessions (id), \n\tFOREIGN KEY(step_id) REFERENCES routine_session_steps (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_session_events_session_id ON routine_session_events (session_id)"
        )
        op.execute(
            "CREATE TABLE routine_launch_requests (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tactor_id VARCHAR(32) NOT NULL, \n\troutine_id INTEGER NOT NULL, \n\tsession_id VARCHAR(32) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(session_id) REFERENCES routine_sessions (id)\n)"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_sessions_scope_insert BEFORE INSERT ON routine_sessions WHEN NOT EXISTS (SELECT 1 FROM routines WHERE id=NEW.routine_id AND workspace_id=NEW.workspace_id AND ((profile_id=NEW.profile_id) OR (profile_id IS NULL AND NEW.profile_id IS NULL))) BEGIN SELECT RAISE(ABORT, 'Routine scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_sessions_scope_update BEFORE UPDATE ON routine_sessions WHEN NOT EXISTS (SELECT 1 FROM routines WHERE id=NEW.routine_id AND workspace_id=NEW.workspace_id AND ((profile_id=NEW.profile_id) OR (profile_id IS NULL AND NEW.profile_id IS NULL))) BEGIN SELECT RAISE(ABORT, 'Routine scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION routine_sessions_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT EXISTS (SELECT 1 FROM routines WHERE id=NEW.routine_id AND workspace_id=NEW.workspace_id AND ((profile_id=NEW.profile_id) OR (profile_id IS NULL AND NEW.profile_id IS NULL))) THEN RAISE EXCEPTION 'Routine scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER routine_sessions_scope BEFORE INSERT OR UPDATE ON routine_sessions FOR EACH ROW EXECUTE FUNCTION routine_sessions_scope_guard()"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER session_snapshot_immutable BEFORE UPDATE ON routine_sessions WHEN NEW.routine_id IS NOT OLD.routine_id OR NEW.workspace_id IS NOT OLD.workspace_id OR NEW.profile_id IS NOT OLD.profile_id OR NEW.occurrence_id IS NOT OLD.occurrence_id OR NEW.title IS NOT OLD.title OR NEW.description IS NOT OLD.description OR NEW.icon IS NOT OLD.icon OR NEW.color IS NOT OLD.color OR NEW.profile_name IS NOT OLD.profile_name OR NEW.routine_version IS NOT OLD.routine_version OR NEW.started_by IS NOT OLD.started_by OR NEW.started_at IS NOT OLD.started_at BEGIN SELECT RAISE(ABORT, 'Run snapshot is immutable'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION session_snapshot_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.routine_id IS DISTINCT FROM OLD.routine_id OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR NEW.profile_id IS DISTINCT FROM OLD.profile_id OR NEW.occurrence_id IS DISTINCT FROM OLD.occurrence_id OR NEW.title IS DISTINCT FROM OLD.title OR NEW.description IS DISTINCT FROM OLD.description OR NEW.icon IS DISTINCT FROM OLD.icon OR NEW.color IS DISTINCT FROM OLD.color OR NEW.profile_name IS DISTINCT FROM OLD.profile_name OR NEW.routine_version IS DISTINCT FROM OLD.routine_version OR NEW.started_by IS DISTINCT FROM OLD.started_by OR NEW.started_at IS DISTINCT FROM OLD.started_at THEN RAISE EXCEPTION 'Run snapshot is immutable'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER session_snapshot_immutable BEFORE UPDATE ON routine_sessions FOR EACH ROW EXECUTE FUNCTION session_snapshot_immutable_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER step_snapshot_immutable BEFORE UPDATE ON routine_session_steps WHEN NEW.session_id IS NOT OLD.session_id OR NEW.title IS NOT OLD.title OR NEW.description IS NOT OLD.description OR NEW.icon IS NOT OLD.icon OR NEW.position IS NOT OLD.position BEGIN SELECT RAISE(ABORT, 'Run snapshot is immutable'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION step_snapshot_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.session_id IS DISTINCT FROM OLD.session_id OR NEW.title IS DISTINCT FROM OLD.title OR NEW.description IS DISTINCT FROM OLD.description OR NEW.icon IS DISTINCT FROM OLD.icon OR NEW.position IS DISTINCT FROM OLD.position THEN RAISE EXCEPTION 'Run snapshot is immutable'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER step_snapshot_immutable BEFORE UPDATE ON routine_session_steps FOR EACH ROW EXECUTE FUNCTION step_snapshot_immutable_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_sessions_finished_update BEFORE UPDATE ON routine_sessions WHEN OLD.status='completed' BEGIN SELECT RAISE(ABORT, 'Finished run is read-only'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION routine_sessions_finished_update_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.status='completed' THEN RAISE EXCEPTION 'Finished run is read-only'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER routine_sessions_finished_update BEFORE UPDATE ON routine_sessions FOR EACH ROW EXECUTE FUNCTION routine_sessions_finished_update_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_sessions_finished_delete BEFORE DELETE ON routine_sessions WHEN OLD.status='completed' BEGIN SELECT RAISE(ABORT, 'Finished run is read-only'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION routine_sessions_finished_delete_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.status='completed' THEN RAISE EXCEPTION 'Finished run is read-only'; END IF; RETURN OLD; END $$"
        )
        op.execute(
            "CREATE TRIGGER routine_sessions_finished_delete BEFORE DELETE ON routine_sessions FOR EACH ROW EXECUTE FUNCTION routine_sessions_finished_delete_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_session_steps_finished_update BEFORE UPDATE ON routine_session_steps WHEN EXISTS (SELECT 1 FROM routine_sessions WHERE id=OLD.session_id AND status='completed') BEGIN SELECT RAISE(ABORT, 'Finished run is read-only'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION routine_session_steps_finished_update_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF EXISTS (SELECT 1 FROM routine_sessions WHERE id=OLD.session_id AND status='completed') THEN RAISE EXCEPTION 'Finished run is read-only'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER routine_session_steps_finished_update BEFORE UPDATE ON routine_session_steps FOR EACH ROW EXECUTE FUNCTION routine_session_steps_finished_update_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_session_steps_finished_delete BEFORE DELETE ON routine_session_steps WHEN EXISTS (SELECT 1 FROM routine_sessions WHERE id=OLD.session_id AND status='completed') BEGIN SELECT RAISE(ABORT, 'Finished run is read-only'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION routine_session_steps_finished_delete_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF EXISTS (SELECT 1 FROM routine_sessions WHERE id=OLD.session_id AND status='completed') THEN RAISE EXCEPTION 'Finished run is read-only'; END IF; RETURN OLD; END $$"
        )
        op.execute(
            "CREATE TRIGGER routine_session_steps_finished_delete BEFORE DELETE ON routine_session_steps FOR EACH ROW EXECUTE FUNCTION routine_session_steps_finished_delete_guard()"
        )


def downgrade():
    raise RuntimeError(
        "Restore a verified backup to roll back; routine history must not be dropped automatically."
    )
