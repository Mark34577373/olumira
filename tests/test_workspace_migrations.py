"""Upgrade a populated account-era schema without altering legacy care records."""

import tempfile
import unittest
from pathlib import Path
from flask_migrate import upgrade
from sqlalchemy import text, select
from olumira import create_app
from olumira.extensions import db
from olumira.models import Routine, WorkspaceMembership, FamilyWorkspace, AuditEvent
from services.data_transfer import read_snapshot
from support import PASSWORD
from services.authentication import PASSWORD_METHOD
from werkzeug.security import generate_password_hash


class WorkspaceMigrationTests(unittest.TestCase):
    def test_populated_0003_backfill_preserves_unknown_owners_and_completions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            app = create_app({"APP_ENV": "testing", "DATABASE": str(path)})
            with app.app_context():
                upgrade(revision="0003")
                with db.engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO owners (id,created_at) VALUES ('linked-owner','2026-10-16'),('unknown-owner','2026-10-16')"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO users (id,email,password_hash,display_name,email_verified,created_at,updated_at,owner_id,auth_version) VALUES ('11111111111111111111111111111111','fictional-migration@example.com',:password,'Fictional account',true,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'linked-owner',0)"
                        ),
                        {
                            "password": generate_password_hash(
                                PASSWORD, method=PASSWORD_METHOD
                            )
                        },
                    )
                    connection.execute(
                        text(
                            "INSERT INTO routines (id,owner_id,name,category) VALUES (12,'linked-owner','Linked fictional routine','Morning'),(13,'unknown-owner','Unclaimed fictional routine','Morning'),(14,NULL,'Unowned fictional routine','Morning')"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO observations (id,owner_id,activity,date,notes) VALUES (21,'linked-owner','Fictional linked moment','2026-10-16','Preserve exactly'),(22,'unknown-owner','Fictional unclaimed moment','2026-10-16','Keep private')"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO routine_completions (routine_id,completion_date) VALUES (12,'2026-10-16'),(13,'2026-10-16')"
                        )
                    )
                before = read_snapshot(path)
                upgrade()
                self.assertEqual(before, read_snapshot(path))
                self.assertEqual(
                    db.session.get(Routine, 12).workspace_id, "linked-owner"
                )
                self.assertIsNone(db.session.get(Routine, 13).workspace_id)
                self.assertIsNone(db.session.get(Routine, 14).workspace_id)
                self.assertEqual(
                    len(list(db.session.scalars(select(FamilyWorkspace)))), 1
                )
                member = db.session.scalar(select(WorkspaceMembership))
                self.assertEqual((member.user_id, member.role), ("1" * 32, "owner"))
                self.assertEqual(list(db.session.scalars(select(AuditEvent))), [])
                self.assertEqual(
                    db.session.execute(text("PRAGMA foreign_key_check")).all(), []
                )
                upgrade()
                self.assertEqual(before, read_snapshot(path))
                db.session.remove()
                db.engine.dispose()
