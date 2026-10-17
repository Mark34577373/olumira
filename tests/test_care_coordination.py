"""Tasks and recipient-specific handoffs use real CSRF, locks and scopes."""

import concurrent.futures, uuid, unittest
from unittest.mock import patch
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import (
    CaregiverTask as Task,
    CaregiverHandoff as Handoff,
    HandoffRecipient,
    AuditEvent,
    CareProfile,
    WorkspaceMembership,
    Observation,
)
import test_communication as fixtures
from support import post, csrf_token, login


class CareCoordinationTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def values(self, **changes):
        data = dict(
            title="Fictional prepare story cards",
            description="Use the familiar board.",
            profile_id="",
            assigned_to="",
            routine_id="",
            due_at="2030-10-22T08:00",
            timezone="America/Chicago",
            priority="normal",
            creation_key=uuid.uuid4().hex,
            scope_workspace=self.ws,
            version="",
        )
        data.update(changes)
        return data

    def create(self, **changes):
        response = post(self.client, "/care/tasks/new", self.values(**changes))
        self.assertEqual(response.status_code, 302, response.text)
        return response.location.rsplit("/", 1)[1]

    def handoff_values(self, **changes):
        values = dict(
            summary="Fictional handoff: the picture choices are ready.",
            profile_id="",
            recipient=self.other,
            routine_id="",
            observation_id="",
            creation_key=uuid.uuid4().hex,
            scope_workspace=self.ws,
        )
        values.update(changes)
        return values

    def test_create_edit_assignment_status_and_idempotent_completion(self):
        helper = self.shared("caregiver")
        tid = self.create(assigned_to=self.other)
        self.assertIn(
            "Fictional prepare story cards", helper.get("/care/tasks?view=my").text
        )
        self.assertEqual(
            post(
                self.client,
                f"/care/tasks/{tid}/edit",
                self.values(
                    version=1, title="Fictional updated task", assigned_to=self.uid
                ),
            ).status_code,
            302,
        )
        self.assertEqual(
            post(
                self.client, f"/care/tasks/{tid}/edit", self.values(version=1)
            ).status_code,
            409,
        )
        for _ in range(2):
            self.assertEqual(
                post(
                    helper,
                    f"/care/tasks/{tid}/status/completed",
                    dict(scope_workspace=self.ws, version=2),
                ).status_code,
                302,
            )
        with self.app.app_context():
            task = db.session.get(Task, tid)
            self.assertEqual(task.status, "completed")
            self.assertEqual(task.completed_by, self.other)
            self.assertIsNotNone(task.completed_at)
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.event_type == "care.task_completed")
                ),
                1,
            )
        self.assertEqual(
            post(
                helper,
                f"/care/tasks/{tid}/status/in_progress",
                dict(scope_workspace=self.ws, version=3),
            ).status_code,
            409,
        )
        self.assertEqual(
            post(
                helper,
                f"/care/tasks/{tid}/status/todo",
                dict(scope_workspace=self.ws, version=3),
            ).status_code,
            302,
        )

    def test_assignment_rejects_viewer_removed_and_unrelated_members(self):
        self.assertEqual(
            post(
                self.client, "/care/tasks/new", self.values(assigned_to=self.other)
            ).status_code,
            422,
        )
        viewer = self.shared("viewer")
        self.assertEqual(
            post(
                self.client, "/care/tasks/new", self.values(assigned_to=self.other)
            ).status_code,
            422,
        )
        tid = self.create()
        self.assertEqual(
            post(
                viewer,
                f"/care/tasks/{tid}/status/completed",
                dict(scope_workspace=self.ws, version=1),
            ).status_code,
            403,
        )
        with self.app.app_context():
            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == self.ws,
                    WorkspaceMembership.user_id == self.other,
                )
            )
            member.role = "caregiver"
            member.status = "revoked"
            db.session.commit()
        self.assertEqual(
            post(
                self.client, "/care/tasks/new", self.values(assigned_to=self.other)
            ).status_code,
            422,
        )
        self.assertEqual(viewer.get(f"/care/tasks/{tid}").status_code, 404)

    def test_recipient_handoff_ack_retries_history_and_task_links(self):
        helper = self.shared("caregiver")
        tid = self.create(assigned_to=self.other)
        values = self.handoff_values(task_ids=[tid])
        created = post(self.client, "/care/handoffs/new", values)
        self.assertEqual(created.status_code, 302, created.text)
        identity = created.location.rsplit("/", 1)[1]
        self.assertEqual(
            post(self.client, "/care/handoffs/new", values).location, created.location
        )
        self.assertEqual(
            post(
                self.client,
                f"/care/handoffs/{identity}/acknowledge",
                dict(scope_workspace=self.ws),
            ).status_code,
            403,
        )
        for _ in range(2):
            self.assertEqual(
                post(
                    helper,
                    f"/care/handoffs/{identity}/acknowledge",
                    dict(scope_workspace=self.ws),
                ).status_code,
                302,
            )
        self.assertIn("Acknowledged", self.client.get(created.location).text)
        self.assertIn(tid, self.client.get(created.location).text)
        with self.app.app_context():
            self.assertIsNotNone(
                db.session.get(HandoffRecipient, (identity, self.other)).acknowledged_at
            )
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.event_type == "care.handoff_acknowledged")
                ),
                1,
            )
        self.assertIn(
            "Fictional handoff",
            self.client.get("/care/handoffs?status=acknowledged").text,
        )
        self.assertNotIn(
            "Fictional handoff:", self.client.get("/care/handoffs?status=pending").text
        )

    def test_team_handoff_has_separate_acknowledgments_and_removed_recipient_history(
        self,
    ):
        self.shared("caregiver")
        third, thirdws = __import__("support").create_user(
            self.app, "fiction-third-caregiver@example.com"
        )
        with self.app.app_context():
            db.session.add(
                WorkspaceMembership(
                    id=uuid.uuid4().hex,
                    workspace_id=self.ws,
                    user_id=third,
                    role="caregiver",
                    status="active",
                )
            )
            db.session.commit()
        created = post(
            self.client, "/care/handoffs/new", self.handoff_values(recipient="team")
        )
        self.assertEqual(created.status_code, 302, created.text)
        identity = created.location.rsplit("/", 1)[1]
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(HandoffRecipient)
                    .where(HandoffRecipient.handoff_id == identity)
                ),
                2,
            )
            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == self.ws,
                    WorkspaceMembership.user_id == third,
                )
            )
            member.status = "revoked"
            db.session.commit()
        self.assertIn(
            "No longer an active caregiver", self.client.get(created.location).text
        )

    def test_scope_csrf_bad_dates_and_reference_validation(self):
        profile = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id=profile,
                    workspace_id=self.otherws,
                    display_name="Fictional other",
                )
            )
            db.session.commit()
        self.assertEqual(
            post(
                self.client, "/care/tasks/new", self.values(profile_id=profile)
            ).status_code,
            404,
        )
        self.assertEqual(
            post(
                self.client, "/care/tasks/new", self.values(routine_id=999999)
            ).status_code,
            404,
        )
        for changes in [
            dict(title=""),
            dict(priority="urgent"),
            dict(timezone="bad/zone"),
            dict(due_at="2030-03-10T02:30"),
        ]:
            self.assertEqual(
                post(
                    self.client, "/care/tasks/new", self.values(**changes)
                ).status_code,
                422,
            )
        self.assertEqual(
            self.client.post("/care/tasks/new", data=self.values()).status_code, 400
        )
        tid = self.create()
        other = self.app.test_client()
        login(other, "fiction-other-board@example.com")
        self.assertEqual(other.get("/care/tasks/" + tid).status_code, 404)
        for path in [
            "/care/tasks?page=0",
            "/care/tasks?view=bad",
            "/care/handoffs?from=bad",
            "/care/activity?page=0",
        ]:
            self.assertEqual(self.client.get(path).status_code, 400, path)

    def test_activity_dashboard_privacy_and_rollback(self):
        self.shared("caregiver")
        tid = self.create(assigned_to=self.uid)
        with self.app.app_context():
            observation = Observation(
                workspace_id=self.ws,
                owner_id=self.ws,
                activity="Fictional observation",
                date="2026-10-17",
                notes="Private fictional note marker",
            )
            db.session.add(observation)
            db.session.commit()
            oid = observation.id
        result = post(
            self.client, "/care/handoffs/new", self.handoff_values(observation_id=oid)
        )
        self.assertEqual(result.status_code, 302, result.text)
        timeline = self.client.get("/care/activity")
        self.assertEqual(timeline.status_code, 200, timeline.text)
        self.assertIn("Handoff created", timeline.text)
        self.assertNotIn("Private fictional note marker", timeline.text)
        self.assertIn(
            "Private fictional note marker",
            self.client.get(f"/care/observations/{oid}").text,
        )
        self.assertIn("Fictional prepare story cards", self.client.get("/").text)
        with patch(
            "services.care_coordination.care_audit",
            side_effect=RuntimeError("fictional failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.create(title="Not committed")
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Task)), 1
            )

    def test_simultaneous_task_updates_conflict_and_same_completion_is_idempotent(self):
        helper = self.shared("caregiver")
        tid = self.create()
        tokens = [csrf_token(c) for c in [self.client, helper]]

        def edit(pair):
            client, token = pair
            return client.post(
                f"/care/tasks/{tid}/edit",
                data=dict(self.values(version=1), csrf_token=token),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(edit, zip([self.client, helper], tokens)))
        self.assertEqual(sorted(r.status_code for r in responses), [302, 409])

        def complete(pair):
            client, token = pair
            return client.post(
                f"/care/tasks/{tid}/status/completed",
                data=dict(scope_workspace=self.ws, version=2, csrf_token=token),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(complete, zip([self.client, helper], tokens)))
        self.assertEqual([r.status_code for r in responses], [302, 302])
        created = post(self.client, "/care/handoffs/new", self.handoff_values())
        identity = created.location.rsplit("/", 1)[1]
        second = self.app.test_client()
        login(second, "fiction-other-board@example.com")
        with second.session_transaction() as selected:
            selected["workspace_id"] = self.ws
        ack_tokens = [csrf_token(client) for client in [helper, second]]

        def ack(pair):
            client, token = pair
            return client.post(
                f"/care/handoffs/{identity}/acknowledge",
                data=dict(scope_workspace=self.ws, csrf_token=token),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(ack, zip([helper, second], ack_tokens)))
        self.assertEqual([r.status_code for r in results], [302, 302])
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.event_type == "care.handoff_acknowledged")
                ),
                1,
            )
