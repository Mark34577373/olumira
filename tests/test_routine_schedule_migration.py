"""A populated Day 22 database survives both additive migrations byte-for-value."""

import tempfile, unittest
from pathlib import Path
from flask_migrate import upgrade
from sqlalchemy import text, inspect
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from olumira import create_app
from olumira.extensions import db
from support import create_user


class ScheduleMigrationTests(unittest.TestCase):
    def test_populated_0007_all_existing_columns_rows_and_constraints_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                {"APP_ENV": "testing", "DATABASE": str(Path(directory) / "old.db")}
            )
            with app.app_context():
                upgrade(revision="0007")
            user, workspace = create_user(app, "fictional-migration-runs@example.com")
            with app.app_context():
                with db.engine.begin() as connection:
                    rid = connection.execute(
                        text("SELECT id FROM routines LIMIT 1")
                    ).scalar()
                    connection.execute(
                        text(
                            "INSERT INTO routine_completions (routine_id,completion_date) VALUES (:id,'2026-10-16')"
                        ),
                        dict(id=rid),
                    )
                    connection.execute(
                        text(
                            "INSERT INTO observations (workspace_id,owner_id,activity,date,notes) VALUES (:ws,:ws,'Fictional migration observation','2026-10-16','Fictional only')"
                        ),
                        dict(ws=workspace),
                    )

                def snapshot():
                    result = {}
                    with db.engine.connect() as connection:
                        for table in inspect(connection).get_table_names():
                            if table not in {"alembic_version", "sqlite_sequence"}:
                                result[table] = sorted(
                                    [
                                        tuple(row)
                                        for row in connection.execute(
                                            text(f'SELECT * FROM "{table}"')
                                        )
                                    ],
                                    key=repr,
                                )
                    return result

                before = snapshot()
                upgrade(revision="0008")
                upgrade()
                upgrade()
                after = snapshot()
                self.assertEqual({table: after[table] for table in before}, before)
                with db.engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(text("PRAGMA foreign_key_check")).all(), []
                    )
                    self.assertEqual(
                        connection.execute(text("PRAGMA integrity_check")).scalar(),
                        "ok",
                    )
                    self.assertEqual(
                        compare_metadata(
                            MigrationContext.configure(connection), db.metadata
                        ),
                        [],
                    )
                db.session.remove()
                db.engine.dispose()
