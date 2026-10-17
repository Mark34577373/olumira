"""Additive routine schedules tables; no legacy rewrites."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "CREATE TABLE routine_schedules (\n\tid VARCHAR(32) NOT NULL, \n\troutine_id INTEGER NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tstate VARCHAR(12) NOT NULL, \n\tversion INTEGER NOT NULL, \n\trevision INTEGER NOT NULL, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_schedule_state CHECK (state IN ('active','paused','ended')), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_schedules_routine_id ON routine_schedules (routine_id)"
        )
        op.execute(
            "CREATE INDEX ix_routine_schedules_workspace_id ON routine_schedules (workspace_id)"
        )
        op.execute(
            "CREATE TABLE routine_schedule_revisions (\n\tid VARCHAR(32) NOT NULL, \n\tschedule_id VARCHAR(32) NOT NULL, \n\tnumber INTEGER NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tlocal_time VARCHAR(5) NOT NULL, \n\tfrequency VARCHAR(12) NOT NULL, \n\tweekdays VARCHAR(13) NOT NULL, \n\tstart_date VARCHAR(10) NOT NULL, \n\tend_date VARCHAR(10), \n\tvalid_from DATETIME NOT NULL, \n\tvalid_until DATETIME, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_schedule_revision UNIQUE (schedule_id, number), \n\tCONSTRAINT ck_schedule_frequency CHECK (frequency IN ('once','daily','weekdays','weekly')), \n\tFOREIGN KEY(schedule_id) REFERENCES routine_schedules (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_schedule_revisions_schedule_id ON routine_schedule_revisions (schedule_id)"
        )
        op.execute(
            "CREATE TABLE routine_occurrences (\n\tid VARCHAR(64) NOT NULL, \n\trevision_id VARCHAR(32) NOT NULL, \n\troutine_id INTEGER NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tscheduled_at DATETIME NOT NULL, \n\tlocal_date VARCHAR(10) NOT NULL, \n\tlocal_time VARCHAR(5) NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_occurrence_day UNIQUE (revision_id, local_date), \n\tFOREIGN KEY(revision_id) REFERENCES routine_schedule_revisions (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_occurrences_scheduled_at ON routine_occurrences (scheduled_at)"
        )
        op.execute(
            "CREATE INDEX ix_routine_occurrences_workspace_id ON routine_occurrences (workspace_id)"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE TABLE routine_schedules (\n\tid VARCHAR(32) NOT NULL, \n\troutine_id INTEGER NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tstate VARCHAR(12) NOT NULL, \n\tversion INTEGER NOT NULL, \n\trevision INTEGER NOT NULL, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_schedule_state CHECK (state IN ('active','paused','ended')), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_schedules_routine_id ON routine_schedules (routine_id)"
        )
        op.execute(
            "CREATE INDEX ix_routine_schedules_workspace_id ON routine_schedules (workspace_id)"
        )
        op.execute(
            "CREATE TABLE routine_schedule_revisions (\n\tid VARCHAR(32) NOT NULL, \n\tschedule_id VARCHAR(32) NOT NULL, \n\tnumber INTEGER NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tlocal_time VARCHAR(5) NOT NULL, \n\tfrequency VARCHAR(12) NOT NULL, \n\tweekdays VARCHAR(13) NOT NULL, \n\tstart_date VARCHAR(10) NOT NULL, \n\tend_date VARCHAR(10), \n\tvalid_from TIMESTAMP WITH TIME ZONE NOT NULL, \n\tvalid_until TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_schedule_revision UNIQUE (schedule_id, number), \n\tCONSTRAINT ck_schedule_frequency CHECK (frequency IN ('once','daily','weekdays','weekly')), \n\tFOREIGN KEY(schedule_id) REFERENCES routine_schedules (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_schedule_revisions_schedule_id ON routine_schedule_revisions (schedule_id)"
        )
        op.execute(
            "CREATE TABLE routine_occurrences (\n\tid VARCHAR(64) NOT NULL, \n\trevision_id VARCHAR(32) NOT NULL, \n\troutine_id INTEGER NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tscheduled_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tlocal_date VARCHAR(10) NOT NULL, \n\tlocal_time VARCHAR(5) NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_occurrence_day UNIQUE (revision_id, local_date), \n\tFOREIGN KEY(revision_id) REFERENCES routine_schedule_revisions (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_routine_occurrences_scheduled_at ON routine_occurrences (scheduled_at)"
        )
        op.execute(
            "CREATE INDEX ix_routine_occurrences_workspace_id ON routine_occurrences (workspace_id)"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_schedules_scope_insert BEFORE INSERT ON routine_schedules WHEN NOT EXISTS (SELECT 1 FROM routines WHERE id=NEW.routine_id AND workspace_id=NEW.workspace_id AND ((profile_id=NEW.profile_id) OR (profile_id IS NULL AND NEW.profile_id IS NULL))) BEGIN SELECT RAISE(ABORT, 'Routine scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_schedules_scope_update BEFORE UPDATE ON routine_schedules WHEN NOT EXISTS (SELECT 1 FROM routines WHERE id=NEW.routine_id AND workspace_id=NEW.workspace_id AND ((profile_id=NEW.profile_id) OR (profile_id IS NULL AND NEW.profile_id IS NULL))) BEGIN SELECT RAISE(ABORT, 'Routine scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION routine_schedules_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT EXISTS (SELECT 1 FROM routines WHERE id=NEW.routine_id AND workspace_id=NEW.workspace_id AND ((profile_id=NEW.profile_id) OR (profile_id IS NULL AND NEW.profile_id IS NULL))) THEN RAISE EXCEPTION 'Routine scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER routine_schedules_scope BEFORE INSERT OR UPDATE ON routine_schedules FOR EACH ROW EXECUTE FUNCTION routine_schedules_scope_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_occurrences_scope_insert BEFORE INSERT ON routine_occurrences WHEN NOT EXISTS (SELECT 1 FROM routines WHERE id=NEW.routine_id AND workspace_id=NEW.workspace_id AND ((profile_id=NEW.profile_id) OR (profile_id IS NULL AND NEW.profile_id IS NULL))) BEGIN SELECT RAISE(ABORT, 'Routine scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER routine_occurrences_scope_update BEFORE UPDATE ON routine_occurrences WHEN NOT EXISTS (SELECT 1 FROM routines WHERE id=NEW.routine_id AND workspace_id=NEW.workspace_id AND ((profile_id=NEW.profile_id) OR (profile_id IS NULL AND NEW.profile_id IS NULL))) BEGIN SELECT RAISE(ABORT, 'Routine scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION routine_occurrences_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT EXISTS (SELECT 1 FROM routines WHERE id=NEW.routine_id AND workspace_id=NEW.workspace_id AND ((profile_id=NEW.profile_id) OR (profile_id IS NULL AND NEW.profile_id IS NULL))) THEN RAISE EXCEPTION 'Routine scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER routine_occurrences_scope BEFORE INSERT OR UPDATE ON routine_occurrences FOR EACH ROW EXECUTE FUNCTION routine_occurrences_scope_guard()"
        )


def downgrade():
    raise RuntimeError(
        "Restore a verified backup to roll back; routine history must not be dropped automatically."
    )
