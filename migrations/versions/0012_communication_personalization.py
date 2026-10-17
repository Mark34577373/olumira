"""Additive profile personalization/caregiver workflows; no legacy rewrites."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            "CREATE TABLE communication_preferences (\n\tprofile_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tcard_size VARCHAR(12) NOT NULL, \n\tlayout VARCHAR(12) NOT NULL, \n\ttext_position VARCHAR(12) NOT NULL, \n\tshow_text BOOLEAN NOT NULL, \n\tshow_symbols BOOLEAN NOT NULL, \n\tspeech_enabled BOOLEAN NOT NULL, \n\tspeech_rate VARCHAR(5) NOT NULL, \n\tvoice_id VARCHAR(300) NOT NULL, \n\tsimplified BOOLEAN NOT NULL, \n\thigh_contrast BOOLEAN NOT NULL, \n\treduced_motion BOOLEAN NOT NULL, \n\tdefault_board_id VARCHAR(32), \n\tversion INTEGER NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (profile_id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(default_board_id) REFERENCES communication_boards (id) ON DELETE SET NULL\n)"
        )
        op.execute(
            "CREATE INDEX ix_communication_preferences_workspace_id ON communication_preferences (workspace_id)"
        )
        op.execute(
            "CREATE TABLE favorite_communication_cards (\n\tprofile_id VARCHAR(32) NOT NULL, \n\tcard_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tPRIMARY KEY (profile_id, card_id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(card_id) REFERENCES communication_cards (id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id)\n)"
        )
        op.execute(
            "CREATE TABLE favorite_communication_phrases (\n\tprofile_id VARCHAR(32) NOT NULL, \n\tphrase_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tPRIMARY KEY (profile_id, phrase_id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(phrase_id) REFERENCES saved_communication_phrases (id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id)\n)"
        )
        op.execute(
            "CREATE TRIGGER communication_preferences_profile_insert BEFORE INSERT ON communication_preferences WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER communication_preferences_profile_update BEFORE UPDATE ON communication_preferences WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER favorite_communication_cards_profile_insert BEFORE INSERT ON favorite_communication_cards WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER favorite_communication_cards_profile_update BEFORE UPDATE ON favorite_communication_cards WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER favorite_communication_phrases_profile_insert BEFORE INSERT ON favorite_communication_phrases WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
        op.execute(
            "CREATE TRIGGER favorite_communication_phrases_profile_update BEFORE UPDATE ON favorite_communication_phrases WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE TABLE communication_preferences (\n\tprofile_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tcard_size VARCHAR(12) NOT NULL, \n\tlayout VARCHAR(12) NOT NULL, \n\ttext_position VARCHAR(12) NOT NULL, \n\tshow_text BOOLEAN NOT NULL, \n\tshow_symbols BOOLEAN NOT NULL, \n\tspeech_enabled BOOLEAN NOT NULL, \n\tspeech_rate VARCHAR(5) NOT NULL, \n\tvoice_id VARCHAR(300) NOT NULL, \n\tsimplified BOOLEAN NOT NULL, \n\thigh_contrast BOOLEAN NOT NULL, \n\treduced_motion BOOLEAN NOT NULL, \n\tdefault_board_id VARCHAR(32), \n\tversion INTEGER NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (profile_id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id), \n\tFOREIGN KEY(default_board_id) REFERENCES communication_boards (id) ON DELETE SET NULL\n)"
        )
        op.execute(
            "CREATE INDEX ix_communication_preferences_workspace_id ON communication_preferences (workspace_id)"
        )
        op.execute(
            "CREATE TABLE favorite_communication_cards (\n\tprofile_id VARCHAR(32) NOT NULL, \n\tcard_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tPRIMARY KEY (profile_id, card_id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(card_id) REFERENCES communication_cards (id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id)\n)"
        )
        op.execute(
            "CREATE TABLE favorite_communication_phrases (\n\tprofile_id VARCHAR(32) NOT NULL, \n\tphrase_id VARCHAR(32) NOT NULL, \n\tworkspace_id VARCHAR(32) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tPRIMARY KEY (profile_id, phrase_id), \n\tFOREIGN KEY(profile_id) REFERENCES care_profiles (id), \n\tFOREIGN KEY(phrase_id) REFERENCES saved_communication_phrases (id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id) REFERENCES family_workspaces (id)\n)"
        )
        op.execute(
            "CREATE TRIGGER communication_preferences_profile_scope BEFORE INSERT OR UPDATE ON communication_preferences FOR EACH ROW EXECUTE FUNCTION olumira_profile_scope()"
        )
        op.execute(
            "CREATE TRIGGER favorite_communication_cards_profile_scope BEFORE INSERT OR UPDATE ON favorite_communication_cards FOR EACH ROW EXECUTE FUNCTION olumira_profile_scope()"
        )
        op.execute(
            "CREATE TRIGGER favorite_communication_phrases_profile_scope BEFORE INSERT OR UPDATE ON favorite_communication_phrases FOR EACH ROW EXECUTE FUNCTION olumira_profile_scope()"
        )

    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER default_board_insert BEFORE INSERT ON communication_preferences WHEN NEW.default_board_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM communication_boards b WHERE b.id=NEW.default_board_id AND b.workspace_id=NEW.workspace_id AND b.profile_id=NEW.profile_id) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER default_board_update BEFORE UPDATE ON communication_preferences WHEN NEW.default_board_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM communication_boards b WHERE b.id=NEW.default_board_id AND b.workspace_id=NEW.workspace_id AND b.profile_id=NEW.profile_id) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION default_board_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.default_board_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM communication_boards b WHERE b.id=NEW.default_board_id AND b.workspace_id=NEW.workspace_id AND b.profile_id=NEW.profile_id) THEN RAISE EXCEPTION 'Care reference scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER default_board BEFORE INSERT OR UPDATE ON communication_preferences FOR EACH ROW EXECUTE FUNCTION default_board_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER card_scope_insert BEFORE INSERT ON favorite_communication_cards WHEN NOT EXISTS (SELECT 1 FROM communication_cards c JOIN communication_boards b ON b.id=c.board_id WHERE c.id=NEW.card_id AND b.workspace_id=NEW.workspace_id AND b.profile_id=NEW.profile_id) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER card_scope_update BEFORE UPDATE ON favorite_communication_cards WHEN NOT EXISTS (SELECT 1 FROM communication_cards c JOIN communication_boards b ON b.id=c.board_id WHERE c.id=NEW.card_id AND b.workspace_id=NEW.workspace_id AND b.profile_id=NEW.profile_id) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION card_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT EXISTS (SELECT 1 FROM communication_cards c JOIN communication_boards b ON b.id=c.board_id WHERE c.id=NEW.card_id AND b.workspace_id=NEW.workspace_id AND b.profile_id=NEW.profile_id) THEN RAISE EXCEPTION 'Care reference scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER card_scope BEFORE INSERT OR UPDATE ON favorite_communication_cards FOR EACH ROW EXECUTE FUNCTION card_scope_guard()"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER phrase_scope_insert BEFORE INSERT ON favorite_communication_phrases WHEN NOT EXISTS (SELECT 1 FROM saved_communication_phrases p WHERE p.id=NEW.phrase_id AND p.workspace_id=NEW.workspace_id AND p.profile_id=NEW.profile_id) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "sqlite":
        op.execute(
            "CREATE TRIGGER phrase_scope_update BEFORE UPDATE ON favorite_communication_phrases WHEN NOT EXISTS (SELECT 1 FROM saved_communication_phrases p WHERE p.id=NEW.phrase_id AND p.workspace_id=NEW.workspace_id AND p.profile_id=NEW.profile_id) BEGIN SELECT RAISE(ABORT, 'Care reference scope mismatch'); END"
        )
    if dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION phrase_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT EXISTS (SELECT 1 FROM saved_communication_phrases p WHERE p.id=NEW.phrase_id AND p.workspace_id=NEW.workspace_id AND p.profile_id=NEW.profile_id) THEN RAISE EXCEPTION 'Care reference scope mismatch'; END IF; RETURN NEW; END $$"
        )
        op.execute(
            "CREATE TRIGGER phrase_scope BEFORE INSERT OR UPDATE ON favorite_communication_phrases FOR EACH ROW EXECUTE FUNCTION phrase_scope_guard()"
        )


def downgrade():
    raise RuntimeError(
        "Restore a reviewed backup; care history/preferences are not automatically deleted."
    )
