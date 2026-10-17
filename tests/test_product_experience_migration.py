"""Populated pre-calendar data survives all four additive milestone migrations."""

import tempfile, unittest
from pathlib import Path
from sqlalchemy import text, inspect, select, func
from sqlalchemy.exc import IntegrityError
from flask_migrate import upgrade
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from olumira import create_app
from olumira.extensions import db
from olumira.models import OnboardingState, Resource, CareProfile, CalendarEvent
from support import create_user


class ProductMigrationTests(unittest.TestCase):
    def test_preservation_seed_legacy_exemption_and_scope_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(
                dict(APP_ENV="testing", DATABASE=str(Path(folder) / "migration.db"))
            )
            with app.app_context():
                upgrade(revision="0014")
            uid, ws = create_user(app, "fictional-legacy-setup@example.com")
            other, foreign = create_user(app, "fictional-foreign-setup@example.com")
            with app.app_context():
                with db.engine.begin() as c:
                    c.execute(
                        text(
                            "INSERT INTO observations(workspace_id,owner_id,activity,date,notes) VALUES (:ws,:ws,'Fictional preserved observation','2026-10-17','Original private note')"
                        ),
                        dict(ws=ws),
                    )
                original = {}
                with db.engine.connect() as c:
                    for table in inspect(c).get_table_names():
                        if table not in ["alembic_version", "sqlite_sequence"]:
                            columns = [
                                col["name"] for col in inspect(c).get_columns(table)
                            ]
                            original[table] = (
                                columns,
                                c.execute(text(f'SELECT * FROM "{table}"')).fetchall(),
                            )
                upgrade()
                upgrade()
                with db.engine.connect() as c:
                    for table, (columns, rows) in original.items():
                        selected = ",".join('"' + key + '"' for key in columns)
                        self.assertEqual(
                            c.execute(
                                text(f'SELECT {selected} FROM "{table}"')
                            ).fetchall(),
                            rows,
                            table,
                        )
                    self.assertEqual(
                        c.execute(text("PRAGMA foreign_key_check")).all(), []
                    )
                    self.assertEqual(
                        compare_metadata(MigrationContext.configure(c), db.metadata), []
                    )
                state = db.session.get(OnboardingState, (uid, ws))
                self.assertTrue(state.legacy_exempt)
                self.assertIsNone(state.completed_at)
                self.assertEqual(
                    db.session.scalar(select(func.count()).select_from(Resource)), 14
                )
                db.session.add(
                    CareProfile(
                        id="f" * 32,
                        workspace_id=foreign,
                        display_name="Fictional other profile",
                    )
                )
                db.session.commit()
                with self.assertRaises(IntegrityError):
                    db.session.add(
                        CalendarEvent(
                            id="e" * 32,
                            workspace_id=ws,
                            profile_id="f" * 32,
                            title="Invalid scope",
                            start_date="2030-01-01",
                            local_time="09:00",
                            end_date="2030-01-01",
                            end_time="10:00",
                            timezone="UTC",
                            created_by=uid,
                        )
                    )
                    db.session.commit()
                db.session.rollback()
                with self.assertRaises(IntegrityError):
                    state = db.session.get(OnboardingState, (uid, ws))
                    state.profile_id = "f" * 32
                    db.session.commit()
                db.session.rollback()
                db.session.remove()
                db.engine.dispose()
