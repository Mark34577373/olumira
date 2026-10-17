"""An additive upgrade must preserve every column in every pre-existing row."""

import tempfile, unittest, sqlite3
from pathlib import Path
from flask_migrate import upgrade
from sqlalchemy import text
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from olumira import create_app
from olumira.extensions import db


class JournalMigrationTests(unittest.TestCase):
    def test_existing_records_and_foreign_keys_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(
                dict(APP_ENV="testing", DATABASE=str(Path(folder) / "migration.db"))
            )
            with app.app_context():
                upgrade(revision="0013")
                db.session.execute(
                    text(
                        "INSERT INTO owners(id,created_at) VALUES ('fictional','2026-10-17')"
                    )
                )
                db.session.execute(
                    text(
                        "INSERT INTO observations(owner_id,activity,date,notes,mood,tags) VALUES ('fictional','Legacy Ω moment','2026-10-16','Original note','Calm','Original')"
                    )
                )
                db.session.commit()
                connection = db.engine.raw_connection()
                cursor = connection.cursor()
                tables = [
                    r[0]
                    for r in cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence')"
                    )
                ]
                before = {}
                for table in tables:
                    columns = [
                        r[1] for r in cursor.execute(f'PRAGMA table_info("{table}")')
                    ]
                    before[table] = (
                        columns,
                        cursor.execute(f'SELECT * FROM "{table}"').fetchall(),
                    )
                connection.close()
                upgrade()
                upgrade()
                with db.engine.connect() as c:
                    for table, (columns, rows) in before.items():
                        actual = c.execute(
                            text(
                                "SELECT "
                                + ",".join('"' + v + '"' for v in columns)
                                + ' FROM "'
                                + table
                                + '"'
                            )
                        ).fetchall()
                        self.assertEqual(actual, rows, table)
                    row = c.execute(
                        text(
                            "SELECT author_id,observed_at,created_at,category,version FROM observations"
                        )
                    ).one()
                    self.assertEqual(tuple(row), (None, None, None, "General notes", 1))
                    self.assertEqual(
                        c.execute(text("PRAGMA foreign_key_check")).fetchall(), []
                    )
                    self.assertEqual(
                        compare_metadata(MigrationContext.configure(c), db.metadata), []
                    )
