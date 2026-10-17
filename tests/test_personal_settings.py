import unittest
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import UserPreference, User
import test_communication as fixtures
from support import post, login


class PersonalSettingsTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def values(self, **changes):
        result = dict(
            version="0",
            display_name="Fictional Fern",
            calendar_view="week",
            week_start="sunday",
            time_format="12",
            reduced_motion="on",
            larger_text="on",
            enhanced_contrast="on",
            reduced_effects="on",
            simplified="on",
        )
        result.update(changes)
        return result

    def test_persistence_calendar_scope_and_validation(self):
        self.assertEqual(self.client.get("/settings").status_code, 200)
        self.assertEqual(post(self.client, "/settings", self.values()).status_code, 302)
        html = self.client.get("/settings").text
        self.assertIn('data-reduced-motion="true"', html)
        calendar = self.client.get("/calendar?date=2026-10-14").text
        self.assertIn("Open Sunday October 11 2026", calendar)
        self.assertEqual(post(self.client, "/settings", self.values()).status_code, 422)
        self.assertEqual(
            post(
                self.client, "/settings", self.values(version="1", calendar_view="fake")
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post("/settings", data=self.values()).status_code, 400
        )
        other = self.shared("viewer")
        self.assertEqual(
            post(
                other, "/settings", self.values(display_name="Fictional Willow")
            ).status_code,
            302,
        )
        post(self.client, "/auth/logout")
        login(self.client, "fiction-board@example.com")
        self.assertIn('data-larger-text="true"', self.client.get("/settings").text)
        with self.app.app_context():
            self.assertEqual(
                db.session.get(UserPreference, self.uid).calendar_view, "week"
            )
            self.assertEqual(
                db.session.get(User, self.uid).display_name, "Fictional Fern"
            )
            self.assertEqual(
                db.session.get(User, self.other).display_name, "Fictional Willow"
            )
