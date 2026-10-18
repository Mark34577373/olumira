"""Live PostgreSQL modern-tenant and row-lock test; never reuse an existing schema."""

import concurrent.futures
import os
import re
import unittest
from sqlalchemy import inspect, select
from flask_migrate import upgrade
from olumira import create_app
from olumira.extensions import db
from olumira.models import WorkspaceMembership
from support import create_user, login, post, PASSWORD
import test_communication as fixture


@unittest.skipUnless(
    os.getenv("TEST_POSTGRES_SECURITY_URL"),
    "No empty disposable TEST_POSTGRES_SECURITY_URL configured",
)
class PostgreSQLSecurityTests(unittest.TestCase):
    def test_modern_flows_scope_and_single_use_export_under_concurrent_download(self):
        app = create_app(
            dict(
                APP_ENV="testing",
                DATABASE_URL=os.environ["TEST_POSTGRES_SECURITY_URL"],
                AUTH_LOGIN_IP_LIMIT="1000 per hour",
                AUTH_LOGIN_ACCOUNT_LIMIT="1000 per hour",
            )
        )
        try:
            with app.app_context():
                self.assertEqual(
                    inspect(db.engine).get_table_names(),
                    [],
                    "Refusing nonempty PostgreSQL schema",
                )
                upgrade()
            uid, wid = create_user(app, "cedar-pg@example.com")
            other, foreign = create_user(app, "willow-pg@example.com")
            owner = app.test_client()
            login(owner, "cedar-pg@example.com")
            unrelated = app.test_client()
            login(unrelated, "willow-pg@example.com")
            self.ws = wid
            board = post(
                owner,
                "/communication/new",
                fixture.CommunicationTests.values(self, scope_workspace=wid),
            ).location
            self.assertTrue(board)
            self.assertEqual(unrelated.get(board).status_code, 404)
            self.assertEqual(owner.get("/calendar?view=month").status_code, 200)
            page = post(
                owner,
                "/settings/privacy",
                dict(
                    action="export",
                    scope="workspace",
                    scope_workspace=wid,
                    current_password=PASSWORD,
                ),
            )
            self.assertEqual(page.status_code, 200)
            token = re.search('name="download_token" value="([^"]+)"', page.text)[1]
            cookie = owner.get_cookie("olumira_session").value

            def download():
                client = app.test_client()
                client.set_cookie("olumira_session", cookie)
                return post(
                    client, "/settings/privacy/download", dict(download_token=token)
                ).status_code

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: download(), range(2)))
            self.assertEqual(sorted(outcomes), [200, 404])
            self.assertEqual(
                post(
                    unrelated, "/workspaces/select", dict(workspace_id=wid)
                ).status_code,
                404,
            )
            with app.app_context():
                member = db.session.scalar(
                    select(WorkspaceMembership).where(
                        WorkspaceMembership.user_id == uid,
                        WorkspaceMembership.workspace_id == wid,
                    )
                )
                member.status = "revoked"
                db.session.commit()
            self.assertEqual(owner.get(board).status_code, 302)
        finally:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
