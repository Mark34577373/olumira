"""Content-first controls retain existing state, filters and authorization."""

import re, unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import OnboardingState, utcnow
import test_communication as fixture
from support import post


class ContentFirstTests(unittest.TestCase):
    setUp = fixture.CommunicationTests.setUp
    tearDown = fixture.CommunicationTests.tearDown

    def test_calendar_options_and_real_date_presentation(self):
        day = datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
        html = self.client.get("/calendar?date=" + day).text
        self.assertEqual(self.client.get("/calendar").status_code, 200)
        self.assertNotRegex(html, r'<details class="filter-disclosure"\s+open')
        self.assertIn("is-today is-selected", html)
        self.assertIn("calendar-mobile-agenda", html)
        self.assertIn('aria-current="date"', html)
        active = self.client.get(
            "/calendar?type=event&status=all&timezone=UTC&view=week"
        ).text
        self.assertRegex(active, r'<details class="filter-disclosure"\s+open')
        self.assertIn('value="all" selected', active)
        self.assertIn('value="UTC"', active)
        self.assertIn("type=event", active)

    def test_observation_filters_remain_submittable_and_active_visible(self):
        html = self.client.get("/observations").text
        self.assertNotRegex(html, r'<details class="filter-disclosure"\s+open')
        self.assertIn('id="observation-composer"', html)
        self.assertIn('name="tag"', html)
        query = "/observations/timeline?q=fictional&tag=independent&category=Achievements&period=custom&from=2026-10-01&to=2026-10-17&timezone=UTC&status=archived"
        html = self.client.get(query).text
        self.assertRegex(html, r'<details class="filter-disclosure"\s+open')
        for value in ["fictional", "independent", "2026-10-01", "2026-10-17", "UTC"]:
            self.assertIn('value="' + value + '"', html)
        self.assertIn("archived</option>", html)
        self.assertIn("Filters applied", html)

    def test_dashboard_uses_saved_setup_step_and_hides_completed_guidance(self):
        html = self.client.get("/").text
        self.assertIn("Step 1 of 8", html)
        self.assertLess(html.index('class="welcome"'), html.index('class="setup-nudge'))
        self.assertEqual(
            post(
                self.client,
                "/setup",
                dict(step="0", version="0", scope_workspace=self.ws, action="continue"),
            ).status_code,
            302,
        )
        self.assertIn("Step 2 of 8 · Family workspace", self.client.get("/").text)
        with self.app.app_context():
            state = db.session.get(OnboardingState, (self.uid, self.ws))
            state.step = 7
            state.completed_at = utcnow()
            db.session.commit()
        self.assertNotIn('class="setup-nudge', self.client.get("/").text)
        self.assertIn(
            "Today's checklist", __import__("html").unescape(self.client.get("/").text)
        )
