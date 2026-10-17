import unittest, uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import Notification, WorkspaceMembership
import test_communication as fixtures
import test_care_coordination as care_fixture
import test_calendar as calendar_fixture
from support import post
from services.notifications import process_reminders


class NotificationTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def test_assignment_read_dismiss_filters_permissions_and_preferences(self):
        helper = self.shared("caregiver")
        values = care_fixture.CareCoordinationTests.values(self, assigned_to=self.other)
        response = post(self.client, "/care/tasks/new", values)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(post(self.client, "/care/tasks/new", values).status_code, 302)
        html = helper.get("/notifications?state=unread").text
        self.assertIn("A caregiver task was assigned to you", html)
        self.assertNotIn(values["description"], html)
        with self.app.app_context():
            notices = list(db.session.scalars(select(Notification)))
            self.assertEqual(len(notices), 1)
            identity = notices[0].id
        self.assertEqual(
            post(self.client, f"/notifications/{identity}/read").status_code, 404
        )
        self.assertEqual(
            helper.post(f"/notifications/{identity}/read").status_code, 400
        )
        for desired in ["read", "unread", "open", "dismiss"]:
            self.assertEqual(
                post(helper, f"/notifications/{identity}/{desired}").status_code, 302
            )
        self.assertNotIn(
            "A caregiver task was assigned to you", helper.get("/notifications").text
        )
        self.assertEqual(
            post(
                helper,
                "/settings/notifications",
                dict(
                    version="0",
                    scope_workspace=self.ws,
                    categories=["handoff"],
                    retention_days="30",
                ),
            ).status_code,
            302,
        )
        self.assertEqual(
            post(
                self.client,
                "/care/tasks/new",
                care_fixture.CareCoordinationTests.values(self, assigned_to=self.other),
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Notification)), 1
            )
        self.assertEqual(helper.get("/notifications?category=bogus").status_code, 400)
        with self.app.app_context():
            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.user_id == self.other,
                    WorkspaceMembership.workspace_id == self.ws,
                )
            )
            member.status = "revoked"
            db.session.commit()
        self.assertEqual(
            post(helper, f"/notifications/{identity}/open").status_code, 404
        )

    def test_handoff_and_acknowledgement(self):
        helper = self.shared("caregiver")
        values = care_fixture.CareCoordinationTests.handoff_values(self)
        response = post(self.client, "/care/handoffs/new", values)
        self.assertEqual(response.status_code, 302)
        identity = response.location.rsplit("/", 1)[1]
        response = post(
            helper,
            f"/care/handoffs/{identity}/acknowledge",
            dict(scope_workspace=self.ws),
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "A handoff was acknowledged", self.client.get("/notifications").text
        )
        self.assertEqual(post(helper, "/notifications/all/all-read").status_code, 302)
        self.assertNotIn(
            "A handoff is ready for your review",
            helper.get("/notifications?state=unread").text,
        )

    def test_background_recurring_reminder_retry_and_cancel(self):
        values = calendar_fixture.CalendarTests.values(
            self,
            start_date="2030-03-01",
            end_date="2030-03-01",
            frequency="daily",
            repeat_until="2030-03-05",
        )
        response = post(self.client, "/calendar/new", values)
        self.assertEqual(response.status_code, 302)
        now = datetime(2030, 3, 1, 14, 30, tzinfo=timezone.utc)
        with self.app.app_context():
            self.assertEqual(process_reminders(self.app, now), 1)
            self.assertEqual(process_reminders(self.app, now), 0)
            self.assertEqual(process_reminders(self.app, now + timedelta(days=1)), 1)
        self.assertEqual(
            post(
                self.client,
                response.location + "/status/canceled",
                dict(
                    version="1", scope_workspace=self.ws, profile_id="", confirm="yes"
                ),
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertEqual(process_reminders(self.app, now + timedelta(days=2)), 0)

    def test_reschedule_and_disabled_reminder_preferences(self):
        response = post(
            self.client, "/calendar/new", calendar_fixture.CalendarTests.values(self)
        )
        path = response.location
        now = datetime(2030, 3, 1, 14, 30, tzinfo=timezone.utc)
        with self.app.app_context():
            self.assertEqual(process_reminders(self.app, now), 1)
        response = post(
            self.client,
            path + "/edit",
            calendar_fixture.CalendarTests.values(
                self, version="1", local_time="10:00", end_time="11:00"
            ),
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(process_reminders(self.app, now), 0)
            self.assertTrue(db.session.scalar(select(Notification)).dismissed_at)
            self.assertEqual(process_reminders(self.app, now + timedelta(hours=1)), 1)
            self.assertEqual(process_reminders(self.app, now + timedelta(hours=1)), 0)
        self.assertEqual(
            post(
                self.client,
                "/calendar/reminders",
                dict(
                    scope_workspace=self.ws,
                    profile_id="",
                    version="0",
                    lead_minutes="60",
                    categories=["event"],
                ),
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertEqual(process_reminders(self.app, now + timedelta(hours=1)), 0)
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.dismissed_at.is_(None))
                ),
                0,
            )

    def test_routine_reminders_reuse_dst_rules_and_cli(self):
        response = post(
            self.client,
            "/routines/new",
            dict(
                name="Fictional DST routine",
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
                    local_time="02:30",
                    frequency="daily",
                    weekdays=[],
                    start_date="2030-03-08",
                    end_date="2030-03-12",
                    version="",
                ),
            )
        # March 10 has no 02:30 local occurrence in Chicago in 2030.
        with self.app.app_context():
            self.assertEqual(
                process_reminders(
                    self.app, datetime(2030, 3, 10, 8, tzinfo=timezone.utc)
                ),
                0,
            )
            self.assertEqual(
                process_reminders(
                    self.app, datetime(2030, 3, 11, 7, tzinfo=timezone.utc)
                ),
                1,
            )
            self.assertEqual(
                process_reminders(
                    self.app, datetime(2030, 3, 11, 7, tzinfo=timezone.utc)
                ),
                0,
            )
        # Pausing after the occurrence leaves historical calendar rows intact;
        # those historical rows must not produce a new approaching reminder.
        from unittest.mock import patch
        from olumira.models import RoutineSchedule

        with self.app.app_context(), self.app.test_request_context("/"):
            login_user(db.session.get(User, self.uid))
            session["workspace_id"] = self.ws
            resolve_context()
            sid = db.session.scalar(
                select(RoutineSchedule.id).where(RoutineSchedule.routine_id == rid)
            )
            with patch(
                "services.routine_scheduling.utcnow",
                return_value=datetime(2030, 3, 11, 8, tzinfo=timezone.utc),
            ):
                routine_scheduling.change_state(sid, "pause", "1")
        with self.app.app_context():
            self.assertEqual(
                process_reminders(
                    self.app, datetime(2030, 3, 11, 8, tzinfo=timezone.utc)
                ),
                0,
            )
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.dismissed_at.is_(None))
                ),
                0,
            )
        result = self.app.test_cli_runner().invoke(args=["process-reminders"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("in-app reminders", result.output)
