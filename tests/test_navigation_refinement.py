"""Day 40.2: context navigation keeps secure POST and authorized scopes."""

import re
import unittest

import test_workspaces as fixture
from support import post


class NavigationRefinementTests(unittest.TestCase):
    setUp = fixture.WorkspaceTests.setUp
    tearDown = fixture.WorkspaceTests.tearDown
    profile = fixture.WorkspaceTests.profile
    add_member = fixture.WorkspaceTests.add_member
    other_client = fixture.WorkspaceTests.other_client

    def test_context_switching_stays_explicit_private_and_csrf_protected(self):
        pid = self.profile()
        html = self.client.get("/").text
        workspace = re.search(r'<select name="workspace_id".*?</select>', html, re.S)[0]
        self.assertIn(self.workspace, workspace)
        self.assertNotIn(self.other_workspace, workspace)
        self.assertIn("Workspace-wide care", html)
        self.assertIn('method="post" action="/workspaces/select"', html)
        self.assertIn('method="post" action="/workspaces/profiles/select"', html)
        self.assertEqual(self.client.get("/workspaces/select").status_code, 405)
        self.assertEqual(
            self.client.post(
                "/workspaces/select", data={"workspace_id": self.workspace}
            ).status_code,
            400,
        )
        self.assertEqual(
            post(
                self.client,
                "/workspaces/profiles/select",
                dict(profile_id=pid, return_to="calendar"),
            ).location,
            "/calendar",
        )
        with self.client.session_transaction() as state:
            self.assertEqual(state["profile_id"], pid)
        page = self.client.get("/calendar").text
        self.assertIn("Care profile switched.", page)
        self.assertIn(f'value="{pid}" selected', page)
        self.assertEqual(
            post(
                self.client,
                "/workspaces/select",
                dict(workspace_id=self.other_workspace),
            ).status_code,
            404,
        )
        with self.client.session_transaction() as state:
            self.assertEqual(state["workspace_id"], self.workspace)
            self.assertEqual(state["profile_id"], pid)
        post(self.client, "/workspaces/select", dict(workspace_id=self.workspace))
        with self.client.session_transaction() as state:
            self.assertNotIn("profile_id", state)
        self.assertIn(
            "Workspace switched. Workspace-wide care is active.",
            self.client.get("/").text,
        )

    def test_preferences_account_and_secondary_navigation_have_current_state(self):
        routes = [
            "/settings",
            "/auth/settings",
            "/dashboard/preferences",
            "/calendar/reminders",
            "/settings/notifications",
            "/settings/privacy",
            "/workspaces/settings",
        ]
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                nav = re.search(
                    r'<nav class="settings-sections".*?</nav>', response.text, re.S
                )[0]
                self.assertEqual(nav.count('aria-current="page"'), 1)
                self.assertIn(f'href="{route}" aria-current="page"', nav)
        for route, href in [
            ("/observations/insights", "/observations"),
            ("/calendar?view=day", "/calendar"),
            ("/care/handoffs", "/care/tasks"),
            ("/routines/history", "/routines"),
        ]:
            with self.subTest(route=route):
                html = self.client.get(route).text
                nav = re.search(r'<div class="nav-links".*?</div>', html, re.S)[0]
                self.assertIn(f'href="{href}" aria-current="page"', nav)
                self.assertEqual(nav.count('aria-current="page"'), 1)
        for route in [
            "/routines",
            "/routines/calendar",
            "/routines/history",
            "/care/tasks",
            "/care/handoffs",
            "/care/activity",
        ]:
            nav = re.search(
                r'<nav class="routine-subnav".*?</nav>',
                self.client.get(route).text,
                re.S,
            )[0]
            self.assertEqual(nav.count('aria-current="page"'), 1, route)

    def test_sparse_care_actions_do_not_invent_data_or_grant_permissions(self):
        html = self.client.get("/care/tasks").text
        self.assertIn("0 tasks", html)
        self.assertIn("Keep the day connected", html)
        self.assertNotIn('aria-label="Task pages"', html)
        viewer, _, _ = self.add_member(role="viewer")
        html = viewer.get("/care/tasks").text
        self.assertNotIn(">Create task</a>", html)
        self.assertNotIn(">Share a handoff</a>", html)
        self.assertIn(">Review handoffs</a>", html)
        self.assertEqual(viewer.get("/care/tasks/new").status_code, 403)
        self.assertEqual(viewer.get("/care/handoffs/new").status_code, 403)

    def test_calendar_today_preserves_secondary_visibility(self):
        html = self.client.get(
            "/calendar?status=all&type=event&timezone=UTC&view=week"
        ).text
        today = re.search(r'<a class="text-link" href="([^"]+)">Today', html)[1]
        for value in ["status=all", "type=event", "timezone=UTC", "view=week"]:
            self.assertIn(value, today)
