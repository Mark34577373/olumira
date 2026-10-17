"""Preserve populated 0006 routines, long legacy names and actual completion dates."""

import tempfile
import unittest
from pathlib import Path
from flask_migrate import upgrade
from sqlalchemy import select, text
from olumira import create_app
from olumira.extensions import db
from olumira.models import Routine, RoutineStep, RoutineCompletionSnapshot
from services.data_transfer import read_snapshot


class RoutineBuilderMigrationTests(unittest.TestCase):
    def test_populated_0006_preserves_parent_rows_and_legacy_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            app = create_app({"APP_ENV": "testing", "DATABASE": str(path)})
            with app.app_context():
                upgrade(revision="0006")
                long_name = "Fictional legacy name " + ("x" * 120)
                with db.engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO owners (id,created_at) VALUES ('fictional-unclaimed','2026-10-16')"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO routines (id,owner_id,name,category) VALUES (42,'fictional-unclaimed',:name,'Morning'),(43,NULL,'Fictional unowned','General')"
                        ),
                        {"name": long_name},
                    )
                    connection.execute(
                        text(
                            "INSERT INTO routine_completions (routine_id,completion_date) VALUES (42,'2026-10-16'),(42,'2026-10-17')"
                        )
                    )
                before = read_snapshot(path)
                upgrade()
                self.assertEqual(before, read_snapshot(path))
                routine = db.session.get(Routine, 42)
                self.assertIsNone(routine.workspace_id)
                self.assertIsNone(routine.created_by)
                self.assertIsNone(routine.created_at)
                self.assertEqual(routine.version, 1)
                self.assertTrue(routine.is_checklist)
                steps = list(
                    db.session.scalars(
                        select(RoutineStep).where(RoutineStep.routine_id == 42)
                    )
                )
                self.assertEqual(len(steps), 1)
                self.assertEqual(steps[0].title, long_name)
                snapshots = list(
                    db.session.scalars(
                        select(RoutineCompletionSnapshot).where(
                            RoutineCompletionSnapshot.routine_id == 42
                        )
                    )
                )
                self.assertEqual(len(snapshots), 2)
                self.assertEqual(
                    {snapshot.source for snapshot in snapshots}, {"migration"}
                )
                self.assertEqual({snapshot.name for snapshot in snapshots}, {long_name})
                self.assertEqual(
                    db.session.execute(text("PRAGMA foreign_key_check")).all(), []
                )
                upgrade()
                self.assertEqual(before, read_snapshot(path))
                db.session.remove()
                db.engine.dispose()
