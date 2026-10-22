"""Advanced journal behavior, scoped timeline, timestamp and migration regressions."""

import unittest
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import Observation, CareProfile
import test_communication as fixtures
from support import post


class JournalTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def values(self, **changes):
        values = dict(
            activity="Completed Morning Routine Independently",
            date="2026-10-17",
            time="08:30",
            timezone="America/Chicago",
            notes="Fictional everyday moment <script>alert(1)</script>",
            category="Achievements",
            tags="Morning, Independent, morning",
            scope_workspace=self.ws,
            profile_id="",
            version="",
        )
        values.update(changes)
        return values

    def create(self, **changes):
        response = post(self.client, "/observations", self.values(**changes))
        self.assertEqual(response.status_code, 302, response.text)
        with self.app.app_context():
            return db.session.scalar(
                select(Observation.id)
                .where(Observation.workspace_id == self.ws)
                .order_by(Observation.id.desc())
            )

    def test_create_edit_conflict_archive_restore_and_authorship(self):
        oid = self.create()
        path = f"/observations/{oid}"
        with self.app.app_context():
            row = db.session.get(Observation, oid)
            original = (row.author_id, row.created_at)
            self.assertEqual(row.tags, "morning, independent")
            self.assertEqual(row.observed_at.hour, 13)
        html = self.client.get(path).text
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert", html)
        helper = self.shared("caregiver")
        self.assertEqual(
            post(
                helper,
                path + "/edit",
                self.values(version=1, activity="Fictional edited"),
            ).status_code,
            302,
        )
        self.assertEqual(
            post(self.client, path + "/edit", self.values(version=1)).status_code, 409
        )
        with self.app.app_context():
            row = db.session.get(Observation, oid)
            self.assertEqual((row.author_id, row.created_at), original)
            self.assertEqual(row.version, 2)
        action = dict(version=2, scope_workspace=self.ws, profile_id="")
        self.assertEqual(post(self.client, path + "/archive", action).status_code, 302)
        self.assertNotIn(
            "Fictional edited", self.client.get("/observations/timeline").text
        )
        self.assertIn(
            "Fictional edited",
            self.client.get("/observations/timeline?status=archived").text,
        )
        self.assertEqual(
            post(self.client, path + "/restore", dict(action, version=3)).status_code,
            302,
        )
        self.assertIn(
            "Fictional edited", self.client.get("/observations/timeline").text
        )

    def test_validation_references_timezone_roles_and_scope(self):
        oid = self.create()
        path = f"/observations/{oid}"
        outsider = self.app.test_client()
        from support import login

        login(outsider, "fiction-other-board@example.com")
        self.assertEqual(outsider.get(path).status_code, 404)
        self.assertEqual(
            post(outsider, path + "/edit", self.values(version=1)).status_code, 404
        )
        for changes in [
            dict(date="2026-02-30"),
            dict(date="2026-03-08", time="02:30"),
            dict(timezone="Bad/Zone"),
            dict(session_id="a" * 32),
            dict(profile_id="foreign"),
            dict(scope_workspace=self.otherws),
        ]:
            response = post(self.client, "/observations", self.values(**changes))
            self.assertIn(response.status_code, [409, 422])
            self.assertIn("Completed Morning", response.text)
        viewer = self.shared("viewer")
        self.assertEqual(viewer.get(path).status_code, 200)
        self.assertEqual(
            post(viewer, path + "/edit", self.values(version=1)).status_code, 403
        )
        self.assertEqual(
            self.client.post(path + "/archive", data={"version": 1}).status_code, 400
        )
        with self.app.app_context():
            p = CareProfile(
                id="p" * 32, workspace_id=self.ws, display_name="Fictional Fern"
            )
            db.session.add(p)
            db.session.commit()
        post(self.client, "/workspaces/profiles/select", dict(profile_id="p" * 32))
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_combined_search_pagination_literal_wildcards_and_dates(self):
        for i in range(23):
            self.create(
                activity=f"Fictional moment {i:02}", time="23:30", date="2026-10-16"
            )
        self.create(activity="Literal 100% _", category="General notes", tags="other")
        response = self.client.get(
            "/observations/timeline?category=Achievements&tag=independent&from=2026-10-16&to=2026-10-16&period=custom&q=moment"
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("23 matching", response.text)
        self.assertIn("Next page", response.text)
        self.assertIn("Fictional moment 22", response.text)
        self.assertNotIn("Fictional moment 00", response.text)
        second = self.client.get(
            "/observations/timeline?page=2&category=Achievements&tag=independent"
        )
        self.assertIn("Fictional moment 00", second.text)
        self.assertIn(
            "1 matching", self.client.get("/observations/timeline?q=100%25").text
        )
        self.assertIn(
            "0 matching",
            self.client.get(
                "/observations/timeline?from=2026-10-18&to=2026-10-18&period=custom"
            ).text,
        )
        self.assertEqual(
            self.client.get("/observations/timeline?from=bad&to=bad").status_code, 422
        )
        oid = self.create()
        self.assertIn(
            "back_category=Achievements",
            self.client.get("/observations/timeline?category=Achievements").text,
        )


    def test_save_confirmation_requires_a_successful_server_write(self):
        self.assertNotIn('Observation saved.', self.client.get('/observations?saved=1').text)
        rejected=post(self.client,'/observations',self.values(activity=''))
        self.assertEqual(rejected.status_code,422)
        self.assertNotIn('Observation saved.',rejected.text)
        saved=post(self.client,'/observations',self.values(),follow_redirects=True)
        self.assertIn('Observation saved.',saved.text)
        self.assertIn('ui-alert-success',saved.text)
        self.assertNotIn('Observation saved.',self.client.get('/observations?saved=1').text)


class AccessLoggingTests(unittest.TestCase):
    def test_access_query_is_redacted_without_mutating_request(self):
        import logging
        from olumira.privacy_logging import AccessPathFilter

        record = logging.LogRecord(
            "werkzeug",
            logging.INFO,
            "",
            0,
            '"%s" %s %s',
            (
                "GET /observations/timeline?q=fictional-private&tag=private HTTP/1.1",
                200,
                10,
            ),
            None,
        )
        self.assertTrue(AccessPathFilter().filter(record))
        self.assertNotIn("fictional-private", record.getMessage())
        self.assertIn("GET /observations/timeline HTTP/1.1", record.getMessage())
