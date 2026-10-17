"""Additive private communication data; preserve all existing content."""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "CREATE TABLE communication_boards (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\ttitle VARCHAR(80) NOT NULL, \n\tdescription VARCHAR(500) NOT NULL, \n\tcategory VARCHAR(40) NOT NULL, \n\tlayout VARCHAR(12) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tarchived_at DATETIME, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_board_layout CHECK (layout IN ('2','3','4','adaptive')), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_boards_scope_updated ON communication_boards (workspace_id, profile_id, updated_at)"
        )
        op.execute(
            "CREATE TABLE communication_cards (\n\tid VARCHAR(32) NOT NULL, \n\tboard_id VARCHAR(32) NOT NULL, \n\tlabel VARCHAR(60) NOT NULL, \n\tspoken_text VARCHAR(200) NOT NULL, \n\tsymbol VARCHAR(32) NOT NULL, \n\tcolor VARCHAR(16) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_communication_card_position UNIQUE (board_id, position), \n\tCONSTRAINT ck_communication_card_position CHECK (position >= 0), \n\tFOREIGN KEY(board_id) REFERENCES communication_boards (id) ON DELETE CASCADE\n)"
        )
        op.execute(
            "CREATE INDEX ix_communication_cards_board_id ON communication_cards (board_id)"
        )
        op.execute(
            "CREATE TRIGGER communication_boards_profile_insert BEFORE INSERT ON communication_boards WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER communication_boards_profile_update BEFORE UPDATE ON communication_boards WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE TABLE communication_boards (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\ttitle VARCHAR(80) NOT NULL, \n\tdescription VARCHAR(500) NOT NULL, \n\tcategory VARCHAR(40) NOT NULL, \n\tlayout VARCHAR(12) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tarchived_at TIMESTAMP WITH TIME ZONE, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_board_layout CHECK (layout IN ('2','3','4','adaptive')), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_boards_scope_updated ON communication_boards (workspace_id, profile_id, updated_at)"
        )
        op.execute(
            "CREATE TABLE communication_cards (\n\tid VARCHAR(32) NOT NULL, \n\tboard_id VARCHAR(32) NOT NULL, \n\tlabel VARCHAR(60) NOT NULL, \n\tspoken_text VARCHAR(200) NOT NULL, \n\tsymbol VARCHAR(32) NOT NULL, \n\tcolor VARCHAR(16) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_communication_card_position UNIQUE (board_id, position), \n\tCONSTRAINT ck_communication_card_position CHECK (position >= 0), \n\tFOREIGN KEY(board_id) REFERENCES communication_boards (id) ON DELETE CASCADE\n)"
        )
        op.execute(
            "CREATE INDEX ix_communication_cards_board_id ON communication_cards (board_id)"
        )
        op.execute(
            "CREATE TRIGGER communication_boards_profile_scope BEFORE INSERT OR UPDATE ON communication_boards FOR EACH ROW EXECUTE FUNCTION olumira_profile_scope()"
        )


def downgrade():
    raise RuntimeError(
        "Restore a reviewed backup; private communication content is not automatically deleted."
    )
