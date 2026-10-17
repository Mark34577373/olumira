"""Additive core product and premium setup tables; preserve existing records."""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "\nCREATE TABLE dashboard_preferences (\n\tuser_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tpreferred_profile_id VARCHAR(32), \n\tsections VARCHAR(120) NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tPRIMARY KEY (user_id, workspace_id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(preferred_profile_id) REFERENCES care_profiles (id)\n)\n\n"
        )
    if dialect == "postgresql":
        op.execute(
            "\nCREATE TABLE dashboard_preferences (\n\tuser_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tpreferred_profile_id VARCHAR(32), \n\tsections VARCHAR(120) NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tPRIMARY KEY (user_id, workspace_id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(preferred_profile_id) REFERENCES care_profiles (id)\n)\n\n"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER dashboard_preferences_scope_insert BEFORE INSERT ON dashboard_preferences WHEN (NEW.preferred_profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.preferred_profile_id AND p.workspace_id=NEW.workspace_id)) BEGIN SELECT RAISE(ABORT, 'Record scope mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER dashboard_preferences_scope_update BEFORE UPDATE ON dashboard_preferences WHEN (NEW.preferred_profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.preferred_profile_id AND p.workspace_id=NEW.workspace_id)) BEGIN SELECT RAISE(ABORT, 'Record scope mismatch'); END"
        )
    elif dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION check_dashboard_preferences_scope() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF (NEW.preferred_profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.preferred_profile_id AND p.workspace_id=NEW.workspace_id)) THEN RAISE EXCEPTION 'Record scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER dashboard_preferences_scope BEFORE INSERT OR UPDATE ON dashboard_preferences FOR EACH ROW EXECUTE FUNCTION check_dashboard_preferences_scope()"
        )


def downgrade():
    raise RuntimeError("Back up and review new records before any downgrade.")
