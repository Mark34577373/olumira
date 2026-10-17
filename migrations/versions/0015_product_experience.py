"""Additive core product and premium setup tables; preserve existing records."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "\nCREATE TABLE calendar_events (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\ttitle VARCHAR(120) NOT NULL, \n\tdescription VARCHAR(2000) NOT NULL, \n\tstart_date VARCHAR(10) NOT NULL, \n\tlocal_time VARCHAR(5) NOT NULL, \n\tend_date VARCHAR(10) NOT NULL, \n\tend_time VARCHAR(5) NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tall_day BOOLEAN NOT NULL, \n\tfrequency VARCHAR(12) NOT NULL, \n\tweekdays VARCHAR(20) NOT NULL, \n\trepeat_until VARCHAR(10), \n\tassigned_to VARCHAR(32), \n\tstatus VARCHAR(12) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(assigned_to) REFERENCES users (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
        )
        op.execute(
            "CREATE INDEX ix_calendar_scope_start ON calendar_events (workspace_id, profile_id, start_date)"
        )
        op.execute(
            "\nCREATE TABLE reminder_preferences (\n\tuser_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tcontext_key VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tenabled BOOLEAN NOT NULL, \n\tlead_minutes INTEGER NOT NULL, \n\tcategories VARCHAR(60) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tPRIMARY KEY (user_id, workspace_id, context_key), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id)\n)\n\n"
        )
    if dialect == "postgresql":
        op.execute(
            "\nCREATE TABLE calendar_events (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\ttitle VARCHAR(120) NOT NULL, \n\tdescription VARCHAR(2000) NOT NULL, \n\tstart_date VARCHAR(10) NOT NULL, \n\tlocal_time VARCHAR(5) NOT NULL, \n\tend_date VARCHAR(10) NOT NULL, \n\tend_time VARCHAR(5) NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tall_day BOOLEAN NOT NULL, \n\tfrequency VARCHAR(12) NOT NULL, \n\tweekdays VARCHAR(20) NOT NULL, \n\trepeat_until VARCHAR(10), \n\tassigned_to VARCHAR(32), \n\tstatus VARCHAR(12) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(assigned_to) REFERENCES users (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
        )
        op.execute(
            "CREATE INDEX ix_calendar_scope_start ON calendar_events (workspace_id, profile_id, start_date)"
        )
        op.execute(
            "\nCREATE TABLE reminder_preferences (\n\tuser_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tcontext_key VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tenabled BOOLEAN NOT NULL, \n\tlead_minutes INTEGER NOT NULL, \n\tcategories VARCHAR(60) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tPRIMARY KEY (user_id, workspace_id, context_key), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id)\n)\n\n"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER calendar_events_scope_insert BEFORE INSERT ON calendar_events WHEN (NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.profile_id AND p.workspace_id=NEW.workspace_id)) BEGIN SELECT RAISE(ABORT, 'Record scope mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER calendar_events_scope_update BEFORE UPDATE ON calendar_events WHEN (NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.profile_id AND p.workspace_id=NEW.workspace_id)) BEGIN SELECT RAISE(ABORT, 'Record scope mismatch'); END"
        )
    elif dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION check_calendar_events_scope() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF (NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.profile_id AND p.workspace_id=NEW.workspace_id)) THEN RAISE EXCEPTION 'Record scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER calendar_events_scope BEFORE INSERT OR UPDATE ON calendar_events FOR EACH ROW EXECUTE FUNCTION check_calendar_events_scope()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER reminder_preferences_scope_insert BEFORE INSERT ON reminder_preferences WHEN (NEW.context_key<>COALESCE(NEW.profile_id,'') OR (NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.profile_id AND p.workspace_id=NEW.workspace_id))) BEGIN SELECT RAISE(ABORT, 'Record scope mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER reminder_preferences_scope_update BEFORE UPDATE ON reminder_preferences WHEN (NEW.context_key<>COALESCE(NEW.profile_id,'') OR (NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.profile_id AND p.workspace_id=NEW.workspace_id))) BEGIN SELECT RAISE(ABORT, 'Record scope mismatch'); END"
        )
    elif dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION check_reminder_preferences_scope() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF (NEW.context_key<>COALESCE(NEW.profile_id,'') OR (NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.profile_id AND p.workspace_id=NEW.workspace_id))) THEN RAISE EXCEPTION 'Record scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER reminder_preferences_scope BEFORE INSERT OR UPDATE ON reminder_preferences FOR EACH ROW EXECUTE FUNCTION check_reminder_preferences_scope()"
        )


def downgrade():
    raise RuntimeError("Back up and review new records before any downgrade.")
