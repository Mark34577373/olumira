import unittest, uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, event
from olumira.extensions import db
from olumira.models import CareProfile, DashboardPreference
import test_communication as fixtures
from support import post


class PersonalizedDashboardTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def test_statistics_privacy_upcoming_and_query_bound(self):
        day = (
            (datetime.now(ZoneInfo("America/Chicago")) + timedelta(days=1))
            .date()
            .isoformat()
        )
        data = dict(
            title="Fictional dashboard event",
            description="Hidden event notes",
            start_date=day,
            local_time="09:00",
            end_date=day,
            end_time="10:00",
            timezone="America/Chicago",
            frequency="once",
            creation_key=uuid.uuid4().hex,
            scope_workspace=self.ws,
            profile_id="",
        )
        self.assertEqual(post(self.client, "/calendar/new", data).status_code, 302)
        post(
            self.client,
            "/observations",
            dict(
                activity="Fictional private moment",
                date=day,
                notes="Fictional note body stays private",
            ),
        )
        html = self.client.get("/").text
        self.assertIn("Fictional dashboard event", html)
        self.assertIn("Fictional private moment", html)
        self.assertNotIn("Fictional note body stays private", html)
        self.assertIn('id="dashboard-active-count">5', html)
        self.assertIn('id="dashboard-tasks-count">0', html)
        self.assertEqual(html.count("<title>"), 1)
        self.assertNotIn("<title>Dashboard | Olumira<section", html)
        calls = []
        with self.app.app_context():
            engine = db.engine

            def track(*args):
                calls.append(1)

            event.listen(engine, "before_cursor_execute", track)
            try:
                self.assertEqual(self.client.get("/").status_code, 200)
            finally:
                event.remove(engine, "before_cursor_execute", track)
        self.assertLess(len(calls), 100)

    def test_preferences_persist_profile_explicit_switch_and_isolation(self):
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id="p" * 32, workspace_id=self.ws, display_name="Fictional Fern"
                )
            )
            db.session.commit()
        values = dict(
            scope_workspace=self.ws,
            version=0,
            preferred_profile_id="p" * 32,
            sections=["insights"],
            timezone="Pacific/Auckland",
        )
        self.assertEqual(
            post(self.client, "/dashboard/preferences", values).status_code, 302
        )
        self.assertNotIn("<h2>Upcoming schedule</h2>", self.client.get("/").text)
        self.assertIn(
            "Pacific/Auckland", self.client.get("/dashboard/preferences").text
        )
        self.assertEqual(
            post(self.client, "/dashboard/preferences", values).status_code, 409
        )
        self.assertEqual(
            post(self.client, "/dashboard/preferred-profile").status_code, 302
        )
        self.assertIn("Fictional Fern’s day", self.client.get("/").text)
        helper = self.shared("caregiver")
        self.assertIn("<h2>Upcoming schedule</h2>", helper.get("/").text)
        self.assertEqual(
            post(
                self.client,
                "/dashboard/preferences",
                dict(values, version=1, preferred_profile_id="x" * 32),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/dashboard/preferences", data=values).status_code, 400
        )

    def test_viewers_can_personalize_without_mutating_shared_records(self):
        viewer = self.shared("viewer")
        self.assertEqual(
            post(
                viewer,
                "/dashboard/preferences",
                dict(
                    scope_workspace=self.ws,
                    version=0,
                    timezone="UTC",
                    sections=["communication"],
                ),
            ).status_code,
            302,
        )
        self.assertIn("disabled", viewer.get("/").text)
        self.assertEqual(post(viewer, "/calendar/new", {}).status_code, 403)
