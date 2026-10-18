"""Synthetic full-schema backup/restore and explicit containment verification."""

import re
import unittest
from pathlib import Path
from sqlalchemy import select, func
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    User,
    Routine,
    CommunicationBoard,
    AuthSession,
    AccountToken,
    DataExport,
)
from services.data_transfer import backup_sqlite
import test_communication as fixture
from support import post, login, PASSWORD


class RecoveryIntegrityTests(unittest.TestCase):
    setUp = fixture.CommunicationTests.setUp
    tearDown = fixture.CommunicationTests.tearDown
    values = fixture.CommunicationTests.values

    def test_full_backup_restore_and_containment_revoke_cookies_links_and_exports(self):
        board = post(self.client, "/communication/new", self.values()).location
        page = post(
            self.client,
            "/settings/privacy",
            dict(
                action="export",
                scope="workspace",
                scope_workspace=self.ws,
                current_password=PASSWORD,
            ),
        )
        token = re.search('name="download_token" value="([^"]+)"', page.text)[1]
        cookie = self.client.get_cookie("olumira_session").value
        with self.app.app_context():
            db.session.remove()
            source = Path(db.engine.url.database)
            snapshot = backup_sqlite(source, Path(self.temp.name) / "snapshot.db")
        restored_path = backup_sqlite(snapshot, Path(self.temp.name) / "restored.db")
        restored = create_app(
            dict(
                APP_ENV="testing",
                DATABASE=str(restored_path),
                SECRET_KEY=self.app.secret_key,
            )
        )
        try:
            with restored.app_context():
                self.assertEqual(
                    db.session.scalar(select(func.count()).select_from(Routine)), 10
                )
                self.assertEqual(
                    db.session.scalar(
                        select(func.count()).select_from(CommunicationBoard)
                    ),
                    1,
                )
                self.assertIsNotNone(db.session.scalar(select(DataExport)))
                before = db.session.get(User, self.uid).auth_version
            restored_client = restored.test_client()
            restored_client.set_cookie("olumira_session", cookie)
            self.assertEqual(restored_client.get(board).status_code, 200)
            runner = restored.test_cli_runner()
            rejected = runner.invoke(
                args=["security-revoke-access", "--confirm", "wrong"]
            )
            self.assertNotEqual(rejected.exit_code, 0)
            self.assertEqual(restored_client.get(board).status_code, 200)
            result = runner.invoke(
                args=[
                    "security-revoke-access",
                    "--confirm",
                    "REVOKE ALL ACCESS ARTIFACTS",
                ]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(restored_client.get(board).status_code, 302)
            with restored.app_context():
                self.assertEqual(
                    db.session.get(User, self.uid).auth_version, before + 1
                )
                self.assertEqual(
                    db.session.scalar(select(func.count()).select_from(DataExport)), 0
                )
                self.assertEqual(
                    db.session.scalar(
                        select(func.count())
                        .select_from(AuthSession)
                        .where(AuthSession.revoked_at.is_(None))
                    ),
                    0,
                )
                self.assertEqual(
                    db.session.scalar(
                        select(func.count())
                        .select_from(AccountToken)
                        .where(AccountToken.used_at.is_(None))
                    ),
                    0,
                )
                self.assertEqual(
                    db.session.scalar(
                        select(func.count()).select_from(CommunicationBoard)
                    ),
                    1,
                )
            login(restored_client, "fiction-board@example.com")
            self.assertEqual(
                post(
                    restored_client,
                    "/settings/privacy/download",
                    dict(download_token=token),
                ).status_code,
                404,
            )
            # Source and backup were not changed by testing the restored copy.
            self.assertEqual(self.client.get(board).status_code, 200)
        finally:
            with restored.app_context():
                db.session.remove()
                db.engine.dispose()
