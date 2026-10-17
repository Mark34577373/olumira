import unittest, uuid
from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import CalendarEvent, ReminderPreference, CareProfile
import test_communication as fixtures
from support import post, login


class CalendarTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def values(self, **changes):
        values = dict(
            title="Fictional garden visit",
            description="Fictional plan",
            start_date="2030-03-01",
            local_time="09:00",
            end_date="2030-03-01",
            end_time="10:00",
            timezone="America/Chicago",
            frequency="weekly",
            repeat_until="2030-04-30",
            assigned_to="",
            creation_key=uuid.uuid4().hex,
            version="",
            scope_workspace=self.ws,
            profile_id="",
        )
        values.update(changes)
        return values

    def test_create_replay_edit_conflict_cancel_archive_restore(self):
        values = self.values()
        response = post(self.client, "/calendar/new", values)
        self.assertEqual(response.status_code, 302, response.status_code)
        path = response.location
        self.assertEqual(post(self.client, "/calendar/new", values).location, path)
        identity = path.rsplit("/", 1)[1]
        with self.app.app_context():
            self.assertEqual(len(list(db.session.scalars(select(CalendarEvent)))), 1)
        self.assertEqual(
            post(
                self.client,
                path + "/edit",
                self.values(version=1, title="Fictional rescheduled visit"),
            ).status_code,
            302,
        )
        self.assertEqual(
            post(self.client, path + "/edit", self.values(version=1)).status_code, 409
        )
        for desired, version in [("canceled", 2), ("archived", 3), ("active", 4)]:
            self.assertEqual(
                post(
                    self.client,
                    path + "/status/" + desired,
                    dict(
                        version=version,
                        scope_workspace=self.ws,
                        profile_id="",
                        confirm="yes",
                    ),
                ).status_code,
                302,
            )
        self.assertIn(
            "Fictional rescheduled visit",
            self.client.get("/calendar?view=week&date=2030-03-01").text,
        )
        self.assertEqual(self.client.get("/calendar?view=bogus").status_code, 422)

    def test_timezone_recurrence_views_and_reminders(self):
        response = post(
            self.client,
            "/calendar/new",
            self.values(
                start_date="2026-03-01",
                end_date="2026-03-01",
                local_time="02:30",
                end_time="03:30",
                frequency="daily",
                repeat_until="2026-03-10",
            ),
        )
        self.assertEqual(response.status_code, 302)
        for view in ["month", "week", "day", "agenda"]:
            self.assertEqual(
                self.client.get("/calendar?date=2026-03-01&view=" + view).status_code,
                200,
            )
        self.assertNotIn(
            "Fictional garden visit",
            self.client.get("/calendar?date=2026-03-08&view=day").text,
        )
        self.assertIn(
            "Fictional garden visit",
            self.client.get("/calendar?date=2026-03-09&view=day").text,
        )
        self.assertEqual(
            post(
                self.client,
                "/calendar/new",
                self.values(
                    start_date="2026-03-08",
                    end_date="2026-03-08",
                    local_time="02:30",
                    end_time="03:30",
                ),
            ).status_code,
            422,
        )
        options = dict(
            scope_workspace=self.ws,
            profile_id="",
            version=0,
            enabled="on",
            lead_minutes=1440,
            categories=["event", "task"],
        )
        self.assertEqual(
            post(self.client, "/calendar/reminders", options).status_code, 302
        )
        self.assertIn("selected>1 day", self.client.get("/calendar/reminders").text)
        self.assertEqual(
            post(self.client, "/calendar/reminders", options).status_code, 409
        )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(ReminderPreference)).lead_minutes, 1440
            )

    def test_scopes_roles_csrf_and_validation(self):
        path = post(self.client, "/calendar/new", self.values()).location
        outsider = self.app.test_client()
        login(outsider, "fiction-other-board@example.com")
        self.assertEqual(outsider.get(path).status_code, 404)
        viewer = self.shared("viewer")
        self.assertEqual(viewer.get(path).status_code, 200)
        self.assertEqual(post(viewer, "/calendar/new", self.values()).status_code, 403)
        self.assertEqual(
            self.client.post("/calendar/new", data=self.values()).status_code, 400
        )
        for change in [
            dict(profile_id="foreign"),
            dict(assigned_to=self.other),
            dict(end_time="08:00"),
            dict(weekdays=[], frequency="weekdays"),
        ]:
            self.assertIn(
                post(self.client, "/calendar/new", self.values(**change)).status_code,
                [409, 422],
            )
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id="p" * 32, workspace_id=self.ws, display_name="Fictional Fern"
                )
            )
            db.session.commit()
        post(self.client, "/workspaces/profiles/select", dict(profile_id="p" * 32))
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_existing_routines_tasks_and_due_reminders_are_integrated(self):
        response = post(
            self.client,
            "/routines/new",
            dict(
                name="Fictional scheduled routine",
                description="",
                category="Morning",
                icon="sun",
                color="sage",
                profile_id="",
                step_id=[""],
                step_title=["Choose a book"],
                step_description=[""],
                step_icon=["book"],
            ),
        )
        self.assertEqual(response.status_code, 302)
        rid = int(response.location.rsplit("/", 1)[1])
        from flask import session
        from flask_login import login_user
        from olumira.models import User
        from services.workspaces import resolve_context
        from services import routine_scheduling

        with self.app.app_context(), self.app.test_request_context("/"):
            login_user(db.session.get(User, self.uid))
            session["workspace_id"] = self.ws
            resolve_context()
            routine_scheduling.save(
                rid,
                dict(
                    timezone="America/Chicago",
                    local_time="09:00",
                    frequency="daily",
                    weekdays=[],
                    start_date="2030-03-01",
                    end_date="2030-03-03",
                    version="",
                ),
            )
        task = post(
            self.client,
            "/care/tasks/new",
            dict(
                title="Fictional calendar task",
                description="",
                profile_id="",
                assigned_to=self.uid,
                routine_id="",
                due_at="2030-03-01T09:15",
                timezone="America/Chicago",
                priority="normal",
                creation_key=uuid.uuid4().hex,
                scope_workspace=self.ws,
            ),
        )
        self.assertEqual(task.status_code, 302)
        html = self.client.get("/calendar?view=day&date=2030-03-01").text
        self.assertIn("Fictional scheduled routine", html)
        self.assertIn("Fictional calendar task", html)
        with patch(
            "services.calendar.utcnow",
            return_value=datetime(2030, 3, 1, 14, 45, tzinfo=timezone.utc),
        ):
            html = self.client.get("/calendar?view=day&date=2030-03-01").text
            self.assertIn("Due and upcoming reminders", html)
        self.assertNotIn(
            "Fictional calendar task",
            self.client.get("/calendar?view=day&date=2030-03-01&type=routine").text,
        )
