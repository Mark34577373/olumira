"""Optional care profiles, with unknown legacy associations left unassigned."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "care_profiles",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("family_workspaces.id"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("avatar", sa.String(16), nullable=False),
        sa.Column("communication", sa.String(500), nullable=False),
        sa.Column("routine_preferences", sa.String(500), nullable=False),
        sa.Column("interests", sa.String(500), nullable=False),
        sa.Column("support_notes", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "workspace_id", name="uq_profile_workspace"),
    )
    op.create_index("ix_care_profiles_workspace_id", "care_profiles", ["workspace_id"])
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER care_profile_workspace_immutable BEFORE UPDATE OF workspace_id ON care_profiles WHEN NEW.workspace_id != OLD.workspace_id BEGIN SELECT RAISE(ABORT, 'Care profile workspace is immutable'); END"
        )
    for table in ("routines", "observations"):
        if op.get_bind().dialect.name == "sqlite":
            op.execute(
                sa.text(
                    "ALTER TABLE "
                    + table
                    + " ADD COLUMN profile_id VARCHAR(32) REFERENCES care_profiles(id)"
                )
            )
            for action in ("INSERT", "UPDATE"):
                op.execute(
                    sa.text(
                        "CREATE TRIGGER "
                        + table
                        + "_profile_"
                        + action.lower()
                        + " BEFORE "
                        + action
                        + " ON "
                        + table
                        + " WHEN NEW.profile_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM care_profiles WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Profile workspace mismatch'); END"
                    )
                )
        else:
            op.add_column(
                table,
                sa.Column(
                    "profile_id",
                    sa.String(32),
                    sa.ForeignKey("care_profiles.id", name="fk_" + table + "_profile"),
                ),
            )
            op.execute(sa.text("""
                CREATE OR REPLACE FUNCTION olumira_profile_scope() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                    IF NEW.profile_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM care_profiles
                        WHERE id=NEW.profile_id AND workspace_id=NEW.workspace_id
                    ) THEN RAISE EXCEPTION 'Profile workspace mismatch'; END IF;
                    RETURN NEW;
                END $$
            """))
            op.execute(
                "CREATE TRIGGER "
                + table
                + "_profile_scope BEFORE INSERT OR UPDATE ON "
                + table
                + " FOR EACH ROW EXECUTE FUNCTION olumira_profile_scope()"
            )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION olumira_profile_workspace_immutable() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
                IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id THEN
                    RAISE EXCEPTION 'Care profile workspace is immutable';
                END IF;
                RETURN NEW;
            END $$
        """))
        op.execute(
            "CREATE TRIGGER care_profile_workspace_immutable BEFORE UPDATE OF workspace_id ON care_profiles "
            "FOR EACH ROW EXECUTE FUNCTION olumira_profile_workspace_immutable()"
        )


def downgrade():
    raise RuntimeError(
        "Restore a reviewed backup; care profiles are not automatically deleted."
    )
