import json, re, time, unittest
from datetime import timedelta
from sqlalchemy import select, func, text
from olumira.extensions import db
from olumira.models import (
    DataExport,
    User,
    FamilyWorkspace,
    WorkspaceMembership,
    DeletionRequest,
    Notification,
    utcnow,
)
import test_communication as fixtures
from support import post, login, PASSWORD


class PrivacyTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def values(self, **changes):
        result = dict(
            action="export",
            scope="personal",
            scope_workspace=self.ws,
            current_password=PASSWORD,
        )
        result.update(changes)
        return result

    def grant(self, client=None, **changes):
        response = post(
            client or self.client, "/settings/privacy", self.values(**changes)
        )
        self.assertEqual(response.status_code, 200, response.text)
        return re.search('name="download_token" value="([^"]+)"', response.text).group(
            1
        )

    def test_exports_scope_secrets_expiry_single_use_and_role(self):
        self.client.get("/")
        token = self.grant()
        response = post(
            self.client, "/settings/privacy/download", dict(download_token=token)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("private, no-store", response.headers["Cache-Control"])
        payload = json.loads(response.data)
        self.assertEqual(payload["scope"], "personal")
        self.assertNotIn("routines", payload["records"])
        self.assertNotIn("password_hash", response.text)
        self.assertEqual(
            post(
                self.client, "/settings/privacy/download", dict(download_token=token)
            ).status_code,
            404,
        )
        token = self.grant(scope="workspace")
        response = post(
            self.client, "/settings/privacy/download", dict(download_token=token)
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = json.loads(response.data)
        self.assertEqual(len(payload["records"]["routines"]), 5)
        self.assertNotIn(self.otherws, response.text)
        viewer = self.shared("viewer")
        self.assertEqual(
            post(
                viewer, "/settings/privacy", self.values(scope="workspace")
            ).status_code,
            403,
        )
        self.assertEqual(
            post(
                self.client, "/settings/privacy", self.values(current_password="wrong")
            ).status_code,
            422,
        )
        token = self.grant()
        with self.app.app_context():
            for grant in db.session.scalars(
                select(DataExport).where(DataExport.consumed_at.is_(None))
            ):
                grant.expires_at = int(time.time()) - 1
            db.session.commit()
        self.assertEqual(
            post(
                self.client, "/settings/privacy/download", dict(download_token=token)
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/settings/privacy", data=self.values()).status_code, 400
        )

    def test_owner_constraint_transfer_account_closure_and_preserved_history(self):
        self.shared("caregiver")
        self.assertEqual(
            post(
                self.client,
                "/settings/privacy",
                self.values(action="account", confirm="DELETE MY ACCOUNT"),
            ).status_code,
            422,
        )
        self.assertEqual(
            post(
                self.client,
                "/settings/privacy",
                self.values(action="transfer", successor=self.other),
            ).status_code,
            302,
        )
        self.assertEqual(
            post(
                self.client,
                "/settings/privacy",
                self.values(
                    action="account",
                    confirm="DELETE MY ACCOUNT",
                    current_password="wrong",
                ),
            ).status_code,
            422,
        )
        self.assertEqual(
            post(
                self.client,
                "/settings/privacy",
                self.values(action="account", confirm="DELETE MY ACCOUNT"),
            ).status_code,
            302,
        )
        with self.app.app_context():
            user = db.session.get(User, self.uid)
            self.assertIsNotNone(user.closed_at)
            self.assertEqual(user.display_name, "Deleted caregiver")
            self.assertTrue(user.email.endswith("@deleted.invalid"))
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(DeletionRequest)), 1
            )
            self.assertEqual(
                db.session.execute(text("PRAGMA foreign_key_check")).all(), []
            )
            self.assertIsNone(db.session.get(FamilyWorkspace, self.ws).closed_at)
        self.assertEqual(
            post(
                self.client,
                "/auth/login",
                dict(email="fiction-board@example.com", password=PASSWORD),
            ).status_code,
            401,
        )

    def test_workspace_closure_requires_owner_password_and_confirmation(self):
        helper = self.shared("caregiver")
        self.assertEqual(
            post(
                helper,
                "/settings/privacy",
                self.values(action="workspace", confirm="CLOSE WORKSPACE"),
            ).status_code,
            403,
        )
        self.assertEqual(
            post(
                self.client,
                "/settings/privacy",
                self.values(action="workspace", confirm="wrong"),
            ).status_code,
            422,
        )
        self.assertEqual(
            post(
                self.client,
                "/settings/privacy",
                self.values(action="workspace", confirm="CLOSE WORKSPACE"),
            ).status_code,
            302,
        )
        self.assertEqual(
            helper.get("/routines").status_code, 200
        )  # helper falls back to its own workspace
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(FamilyWorkspace, self.ws).closed_at)
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(WorkspaceMembership)
                    .where(
                        WorkspaceMembership.workspace_id == self.ws,
                        WorkspaceMembership.status == "active",
                    )
                ),
                0,
            )
            self.assertEqual(
                db.session.execute(text("PRAGMA foreign_key_check")).all(), []
            )

    def test_account_deletion_after_closing_last_workspace(self):
        self.client.get("/")
        self.assertEqual(
            post(
                self.client,
                "/settings/privacy",
                self.values(action="workspace", confirm="CLOSE WORKSPACE"),
            ).status_code,
            302,
        )
        self.assertEqual(self.client.get("/settings/privacy").status_code, 200)
        self.assertEqual(
            post(
                self.client,
                "/settings/privacy",
                self.values(action="account", confirm="DELETE MY ACCOUNT"),
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(User, self.uid).closed_at)

    def test_retention_only_read_dismissed_and_expired_grants(self):
        from services.privacy import cleanup

        self.client.get("/")
        token = self.grant()
        with self.app.app_context():
            now = utcnow()
            for index, read in enumerate(
                [now - timedelta(days=91), None, now - timedelta(days=1)]
            ):
                db.session.add(
                    Notification(
                        id=str(index),
                        user_id=self.uid,
                        workspace_id=self.ws,
                        category="task",
                        entity_type="task",
                        entity_id="fiction",
                        title="Fictional",
                        dedup_key=str(index),
                        created_at=now - timedelta(days=100),
                        read_at=read,
                    )
                )
            grant = db.session.scalar(select(DataExport))
            grant.expires_at = int(time.time()) - 1
            db.session.commit()
            self.assertEqual(cleanup(now), 2)
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Notification)), 2
            )
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(DataExport)), 0
            )

    def test_export_bound_and_authorization_rechecked_at_download(self):
        from unittest.mock import patch

        self.client.get("/")
        token = self.grant(scope="workspace")
        with patch("services.privacy.MAX_ROWS", 1):
            response = post(
                self.client, "/settings/privacy/download", dict(download_token=token)
            )
            self.assertEqual(response.status_code, 302)
        # A failed bounded generation leaves the grant unconsumed for recovery.
        response = post(
            self.client, "/settings/privacy/download", dict(download_token=token)
        )
        self.assertEqual(response.status_code, 200)
        helper = self.shared("caregiver")
        token = self.grant(scope="workspace")
        self.assertEqual(
            post(
                helper, "/settings/privacy/download", dict(download_token=token)
            ).status_code,
            404,
        )
        with self.app.app_context():
            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == self.ws,
                    WorkspaceMembership.user_id == self.uid,
                )
            )
            member.role = "viewer"
            db.session.commit()
        self.assertEqual(
            post(
                self.client, "/settings/privacy/download", dict(download_token=token)
            ).status_code,
            403,
        )

    def test_closed_account_cannot_create_another_workspace(self):
        from werkzeug.exceptions import Forbidden
        from services.workspaces import create_workspace

        self.client.get("/")
        post(
            self.client,
            "/settings/privacy",
            self.values(action="workspace", confirm="CLOSE WORKSPACE"),
        )
        post(
            self.client,
            "/settings/privacy",
            self.values(action="account", confirm="DELETE MY ACCOUNT"),
        )
        with self.app.app_context():
            with self.assertRaises(Forbidden):
                create_workspace(self.uid, "Fictional forbidden family")
            db.session.rollback()

    def test_membership_change_during_closure_rolls_back_safely(self):
        from unittest.mock import patch
        from services.workspaces import lock_workspace

        self.shared("caregiver")
        post(
            self.client,
            "/settings/privacy",
            self.values(action="transfer", successor=self.other),
        )

        def changed(wid):
            lock_workspace(wid)
            db.session.add(
                WorkspaceMembership(
                    id="new-relationship",
                    user_id=self.uid,
                    workspace_id=self.otherws,
                    role="caregiver",
                    status="active",
                )
            )
            db.session.flush()

        with patch("services.privacy.lock_workspace", side_effect=changed):
            response = post(
                self.client,
                "/settings/privacy",
                self.values(action="account", confirm="DELETE MY ACCOUNT"),
            )
        self.assertEqual(response.status_code, 422)
        self.assertIn("memberships changed", response.text)
        with self.app.app_context():
            self.assertIsNone(db.session.get(User, self.uid).closed_at)
