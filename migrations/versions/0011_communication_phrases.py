"""Additive private communication data; preserve all existing content."""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "CREATE TABLE saved_communication_phrases (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tlabel VARCHAR(60) NOT NULL, \n\ttext VARCHAR(1000) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tarchived_at DATETIME, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_saved_phrase_position CHECK (position >= 0), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_saved_phrases_scope_order ON saved_communication_phrases (workspace_id, profile_id, position)"
        )
        op.execute(
            "CREATE TRIGGER saved_communication_phrases_profile_insert BEFORE INSERT ON saved_communication_phrases WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER saved_communication_phrases_profile_update BEFORE UPDATE ON saved_communication_phrases WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE TABLE saved_communication_phrases (\n\tid VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tprofile_id VARCHAR(32), \n\tlabel VARCHAR(60) NOT NULL, \n\ttext VARCHAR(1000) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tarchived_at TIMESTAMP WITH TIME ZONE, \n\tcreated_by VARCHAR(32) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_saved_phrase_position CHECK (position >= 0), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
        )
        op.execute(
            "CREATE INDEX ix_saved_phrases_scope_order ON saved_communication_phrases (workspace_id, profile_id, position)"
        )
        op.execute(
            "CREATE TRIGGER saved_communication_phrases_profile_scope BEFORE INSERT OR UPDATE ON saved_communication_phrases FOR EACH ROW EXECUTE FUNCTION olumira_profile_scope()"
        )


def downgrade():
    raise RuntimeError(
        "Restore a reviewed backup; private communication content is not automatically deleted."
    )
