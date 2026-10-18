"""Upgrade a populated 0021 database without losing prior care records."""

import tempfile, unittest, uuid
from pathlib import Path
from flask_migrate import upgrade
from sqlalchemy import text
from olumira import create_app
from olumira.extensions import db
from support import create_historical_user


class CommercialMigrationTests(unittest.TestCase):
    def test_populated_0021_upgrade_keeps_steps_handoffs_and_defaults_timers_off(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(
                dict(APP_ENV="testing", DATABASE=str(Path(folder) / "upgrade.db"))
            )
            with app.app_context():
                upgrade(revision="0021")
            uid, wid = create_historical_user(app, "fictional-migration@example.com")
            from olumira.models import Routine, CaregiverHandoff, RoutineStep

            with app.app_context():
                routine = Routine(
                    workspace_id=wid,
                    owner_id=wid,
                    name="Fictional existing routine",
                    category="Morning",
                )
                db.session.add(routine)
                db.session.commit()
                rid = routine.id
                sid = uuid.uuid4().hex
                hid = uuid.uuid4().hex
                db.session.execute(
                    text(
                        "INSERT INTO routine_steps (id,routine_id,title,description,icon,position,created_at,updated_at) VALUES (:id,:rid,'Fictional existing step','','sun',0,'2026-01-01','2026-01-01')"
                    ),
                    dict(id=sid, rid=rid),
                )
                db.session.add(
                    CaregiverHandoff(
                        id=hid,
                        workspace_id=wid,
                        summary="Fictional existing shared handoff",
                        recipient_kind="person",
                        created_by=uid,
                    )
                )
                db.session.commit()
                old_counts = {
                    name: db.session.execute(
                        text("SELECT count(*) FROM " + name)
                    ).scalar()
                    for name in [
                        "users",
                        "routines",
                        "routine_steps",
                        "caregiver_handoffs",
                    ]
                }
                db.session.rollback()
                upgrade()
                upgrade()
                self.assertEqual(
                    db.session.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalar(),
                    "0022",
                )
                self.assertEqual(db.session.get(RoutineStep, sid).timer_seconds, 0)
                self.assertEqual(
                    db.session.get(CaregiverHandoff, hid).summary,
                    "Fictional existing shared handoff",
                )
                for name, count in old_counts.items():
                    self.assertEqual(
                        db.session.execute(
                            text("SELECT count(*) FROM " + name)
                        ).scalar(),
                        count,
                    )
                self.assertEqual(
                    db.session.execute(text("PRAGMA foreign_key_check")).all(), []
                )
                db.session.remove()
                db.engine.dispose()
