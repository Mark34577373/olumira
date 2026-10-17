"""Additive core product and premium setup tables; preserve existing records."""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "\nCREATE TABLE onboarding_states (\n\tuser_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tstep INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tprofile_id VARCHAR(32), \n\troutine_id INTEGER, \n\tboard_id VARCHAR(32), \n\tskipped_steps VARCHAR(40) NOT NULL, \n\tstarted_at DATETIME, \n\tcompleted_at DATETIME, \n\tskipped_at DATETIME, \n\tlegacy_exempt BOOLEAN NOT NULL, \n\tPRIMARY KEY (user_id, workspace_id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(board_id) REFERENCES communication_boards (id)\n)\n\n"
        )
    if dialect == "postgresql":
        op.execute(
            "\nCREATE TABLE onboarding_states (\n\tuser_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tstep INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tprofile_id VARCHAR(32), \n\troutine_id INTEGER, \n\tboard_id VARCHAR(32), \n\tskipped_steps VARCHAR(40) NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tskipped_at TIMESTAMP WITH TIME ZONE, \n\tlegacy_exempt BOOLEAN NOT NULL, \n\tPRIMARY KEY (user_id, workspace_id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(routine_id) REFERENCES routines (id), \n\tFOREIGN KEY(board_id) REFERENCES communication_boards (id)\n)\n\n"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER onboarding_states_scope_insert BEFORE INSERT ON onboarding_states WHEN (NEW.step<0 OR NEW.step>7 OR (NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.profile_id AND p.workspace_id=NEW.workspace_id)) OR (NEW.routine_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routines r WHERE r.id=NEW.routine_id AND r.workspace_id=NEW.workspace_id AND r.profile_id IS NEW.profile_id)) OR (NEW.board_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM communication_boards r WHERE r.id=NEW.board_id AND r.workspace_id=NEW.workspace_id AND r.profile_id IS NEW.profile_id))) BEGIN SELECT RAISE(ABORT, 'Record scope mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER onboarding_states_scope_update BEFORE UPDATE ON onboarding_states WHEN (NEW.step<0 OR NEW.step>7 OR (NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.profile_id AND p.workspace_id=NEW.workspace_id)) OR (NEW.routine_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routines r WHERE r.id=NEW.routine_id AND r.workspace_id=NEW.workspace_id AND r.profile_id IS NEW.profile_id)) OR (NEW.board_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM communication_boards r WHERE r.id=NEW.board_id AND r.workspace_id=NEW.workspace_id AND r.profile_id IS NEW.profile_id))) BEGIN SELECT RAISE(ABORT, 'Record scope mismatch'); END"
        )
    elif dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION check_onboarding_states_scope() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF (NEW.step<0 OR NEW.step>7 OR (NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles p WHERE p.id=NEW.profile_id AND p.workspace_id=NEW.workspace_id)) OR (NEW.routine_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM routines r WHERE r.id=NEW.routine_id AND r.workspace_id=NEW.workspace_id AND r.profile_id IS NOT DISTINCT FROM NEW.profile_id)) OR (NEW.board_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM communication_boards r WHERE r.id=NEW.board_id AND r.workspace_id=NEW.workspace_id AND r.profile_id IS NOT DISTINCT FROM NEW.profile_id))) THEN RAISE EXCEPTION 'Record scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER onboarding_states_scope BEFORE INSERT OR UPDATE ON onboarding_states FOR EACH ROW EXECUTE FUNCTION check_onboarding_states_scope()"
        )

    existing = "TRUE" if dialect == "postgresql" else "1"
    op.execute(
        "INSERT INTO onboarding_states (user_id,workspace_id,step,version,skipped_steps,legacy_exempt) SELECT user_id,workspace_id,0,1,'',"
        + existing
        + " FROM workspace_memberships WHERE status='active'"
    )


def downgrade():
    raise RuntimeError("Back up and review new records before any downgrade.")
