import uuid
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import (
    CareProfile,
    CarePlan,
    CareGoal,
    CarePlanRoutine,
    Routine,
    Observation,
)
import test_communication as fixtures
from support import post
import unittest


class CarePlanTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def profile(self):
        identity = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id=identity,
                    workspace_id=self.ws,
                    display_name="Fictional River",
                    avatar="leaf",
                )
            )
            db.session.commit()
        with self.client.session_transaction() as context:
            context["workspace_id"] = self.ws
            context["profile_id"] = identity
        return identity

    def values(self, profile, **changes):
        values = dict(
            scope_workspace=self.ws,
            profile_id=profile,
            title="Fictional familiar day",
            description="Shared support",
            priorities="Clear choices",
            status="active",
            creation_key=uuid.uuid4().hex,
            version="",
        )
        values.update(changes)
        return values

    def test_plan_goals_links_edit_and_scope(self):
        profile = self.profile()
        with self.app.app_context():
            routine = Routine(
                workspace_id=self.ws,
                profile_id=profile,
                name="Fictional sequence",
                category="Morning",
                owner_id=self.ws,
            )
            db.session.add(routine)
            db.session.flush()
            rid = routine.id
            db.session.add(
                Observation(
                    workspace_id=self.ws,
                    profile_id=profile,
                    activity="Fictional moment",
                    date="2030-01-01",
                )
            )
            db.session.commit()
        self.assertEqual(
            post(
                self.client,
                "/care-plans/new",
                self.values(profile, routine_ids=[str(rid), "0" + str(rid)]),
            ).status_code,
            422,
        )
        values = self.values(
            profile, routine_ids=[str(rid)], goal_title="Familiar starts"
        )
        response = post(self.client, "/care-plans/new", values)
        self.assertEqual(response.status_code, 302, response.text)
        url = response.location
        self.assertEqual(post(self.client, "/care-plans/new", values).location, url)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn("Fictional moment", page.text)
        self.assertIn("Familiar starts", page.text)
        plan_id = url.rsplit("/", 1)[1]
        goal_values = dict(
            scope_workspace=self.ws,
            title="Share a choice",
            description="Together",
            category="Communication",
            status="in_progress",
            target_date="2030-03-01",
            version="1",
        )
        self.assertEqual(
            post(self.client, url + "/goals/new", goal_values).status_code, 302
        )
        with self.app.app_context():
            goal = db.session.scalar(
                select(CareGoal).where(CareGoal.title == "Share a choice")
            )
            gid = goal.id
        goal_values.update(version="2", status="completed")
        self.assertEqual(
            post(self.client, url + "/goals/" + gid + "/edit", goal_values).status_code,
            302,
        )
        self.assertEqual(
            post(
                self.client, url + "/edit", self.values(profile, version="1")
            ).status_code,
            409,
        )
        self.assertEqual(
            post(
                self.client, url + "/edit", self.values(profile, version="3")
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertIsNone(
                db.session.scalar(
                    select(CarePlanRoutine).where(CarePlanRoutine.plan_id == plan_id)
                )
            )
        with self.client.session_transaction() as context:
            context["profile_id"] = None
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotIn("Fictional familiar day", self.client.get("/care-plans").text)

    def test_invalid_foreign_links_viewer_and_revocation(self):
        profile = self.profile()
        with self.app.app_context():
            foreign = Routine(
                workspace_id=self.otherws,
                profile_id=None,
                name="PRIVATE foreign routine",
                category="Morning",
                owner_id=self.otherws,
            )
            db.session.add(foreign)
            db.session.commit()
            rid = foreign.id
        self.assertEqual(
            post(
                self.client,
                "/care-plans/new",
                self.values(profile, routine_ids=[str(rid)]),
            ).status_code,
            404,
        )
        self.assertEqual(
            post(
                self.client, "/care-plans/new", self.values(profile, title="")
            ).status_code,
            422,
        )
        response = post(self.client, "/care-plans/new", self.values(profile))
        viewer = self.shared("viewer")
        with viewer.session_transaction() as context:
            context["profile_id"] = profile
        self.assertEqual(viewer.get(response.location).status_code, 200)
        self.assertEqual(viewer.get(response.location + "/edit").status_code, 403)
        self.assertEqual(
            post(viewer, "/care-plans/new", self.values(profile)).status_code, 403
        )
        with self.app.app_context():
            from olumira.models import WorkspaceMembership

            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == self.ws,
                    WorkspaceMembership.user_id == self.other,
                )
            )
            member.status = "revoked"
            db.session.commit()
        self.assertNotEqual(viewer.get(response.location).status_code, 200)

    def test_board_task_links_draft_and_invalid_goal(self):
        from olumira.models import CommunicationBoard, CarePlanBoard, CarePlanTask
        import test_care_coordination as tasks

        profile = self.profile()
        task_values = tasks.CareCoordinationTests.values(self, profile_id=profile)
        response = post(self.client, "/care/tasks/new", task_values)
        self.assertEqual(response.status_code, 302, response.text)
        tid = response.location.rsplit("/", 1)[1]
        bid = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add(
                CommunicationBoard(
                    id=bid,
                    workspace_id=self.ws,
                    profile_id=profile,
                    title="Fictional choices",
                    category="Needs",
                    created_by=self.uid,
                )
            )
            db.session.commit()
        response = post(
            self.client,
            "/care-plans/new",
            self.values(profile, board_ids=[bid], task_ids=[tid], plan_action="draft"),
        )
        self.assertEqual(response.status_code, 302, response.text)
        pid = response.location.rsplit("/", 1)[1]
        with self.app.app_context():
            self.assertEqual(db.session.get(CarePlan, pid).status, "draft")
            self.assertIsNotNone(db.session.get(CarePlanBoard, (pid, bid)))
            self.assertIsNotNone(db.session.get(CarePlanTask, (pid, tid)))
        invalid = dict(
            scope_workspace=self.ws,
            title="Fictional goal",
            description="",
            category="Daily support",
            status="planned",
            target_date="2030-02-31",
            version=1,
        )
        self.assertEqual(
            post(self.client, response.location + "/goals/new", invalid).status_code,
            422,
        )
