import unittest, uuid
from unittest.mock import patch
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import (
    OnboardingState,
    CareProfile,
    Routine,
    CommunicationBoard,
    FamilyWorkspace,
)
import test_communication as fixtures
from support import post, login


class OnboardingTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def current(self):
        self.client.get("/setup")
        with self.client.session_transaction() as session:
            workspace = session.get("workspace_id")
        with self.app.app_context():
            row = db.session.get(OnboardingState, (self.uid, workspace))
            return (row.step, row.version, workspace) if row else (0, 0, workspace)

    def advance(self, **changes):
        step, version, workspace = self.current()
        data = dict(
            step=step, version=version, scope_workspace=workspace, action="continue"
        )
        data.update(changes)
        return post(self.client, "/setup", data)

    def test_new_user_complete_resume_skip_and_no_duplicate_submission(self):
        self.assertIn("Start guided setup", self.client.get("/").text)
        self.assertEqual(self.advance().status_code, 302)
        self.assertEqual(self.current()[0], 1)
        self.client.get("/")
        self.assertIn("Family workspace", self.client.get("/setup").text)
        self.assertEqual(self.advance().status_code, 302)
        step, version, workspace = self.current()
        data = dict(
            step=step,
            version=version,
            scope_workspace=workspace,
            action="continue",
            profile_action="new",
            profile_name="Fictional Fern",
        )
        self.assertEqual(post(self.client, "/setup", data).status_code, 302)
        self.assertEqual(post(self.client, "/setup", data).status_code, 302)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(CareProfile)), 1
            )
        self.assertEqual(self.advance(routine_template="morning").status_code, 302)
        self.assertEqual(self.advance(board_template="needs").status_code, 302)
        self.assertEqual(self.advance(action="skip").status_code, 302)
        self.assertEqual(self.advance().status_code, 302)
        with self.app.app_context():
            state = db.session.get(OnboardingState, (self.uid, self.ws))
            self.assertEqual(state.step, 7)
            self.assertIsNotNone(state.completed_at)
            self.assertEqual(state.skipped_steps, "5")
            self.assertIsNotNone(state.routine_id)
            self.assertIsNotNone(state.board_id)
        self.assertIn("Enter Olumira", self.client.get("/setup").text)
        self.assertNotIn("Start guided setup", self.client.get("/").text)
        self.assertIn("Fictional Fern’s day", self.client.get("/").text)
        for i in range(7):
            self.assertEqual(self.client.get("/tour?step=" + str(i)).status_code, 200)

    def test_workspace_creation_authorization_stale_forms_and_existing_revisit(self):
        self.advance()
        self.assertEqual(
            self.advance(
                workspace_action="new", workspace_name="Fictional Cedar Family"
            ).status_code,
            302,
        )
        _, _, new = self.current()
        self.assertNotEqual(new, self.ws)
        # Simulate a committed response whose new workspace cookie was lost.
        with self.client.session_transaction() as session:
            session["workspace_id"] = self.ws
            session.pop("profile_id", None)
        replay = post(
            self.client,
            "/setup",
            dict(
                step=1,
                version=1,
                scope_workspace=self.ws,
                action="continue",
                workspace_action="new",
                workspace_name="Fictional Cedar Family",
            ),
        )
        self.assertEqual(replay.status_code, 302)
        self.assertEqual(self.current()[2], new)
        self.assertEqual(self.client.post("/setup", data={}).status_code, 400)
        self.assertEqual(self.advance(selected_profile="x" * 32).status_code, 404)
        self.assertEqual(self.advance(step=6).status_code, 409)
        self.assertEqual(self.advance(scope_workspace=self.otherws).status_code, 409)
        self.assertEqual(
            self.advance(profile_action="new", profile_name="").status_code, 422
        )
        self.assertEqual(self.advance(profile_action="existing").status_code, 302)
        self.advance(action="skip")
        self.advance(action="skip")
        self.advance(action="skip")
        self.advance(action="skip")
        step, version, ws = self.current()
        self.assertEqual(
            post(
                self.client,
                "/setup",
                dict(scope_workspace=ws, version=version, action="restart"),
            ).status_code,
            302,
        )
        self.assertEqual(self.current()[0], 0)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(FamilyWorkspace)), 3
            )

    def test_creation_failure_rolls_back_state_and_shared_service_records(self):
        self.advance()
        self.advance()
        self.advance(profile_action="new", profile_name="Fictional Fern")
        with self.app.app_context():
            before = db.session.scalar(select(func.count()).select_from(Routine))
        with patch(
            "services.onboarding.care_audit",
            side_effect=RuntimeError("Fictional failure"),
        ):
            # Complete step uses care_audit; fail at routine creation flush instead.
            with patch(
                "services.routine_builder.care_audit",
                side_effect=ValueError("Fictional service failure"),
            ):
                self.assertEqual(
                    self.advance(routine_template="morning").status_code, 422
                )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Routine)), before
            )
        self.assertEqual(self.current()[0], 3)
        self.assertEqual(self.advance(action="skip").status_code, 302)

    def test_viewer_skip_and_no_creation_or_foreign_profile(self):
        viewer = self.shared("viewer")

        def go(step, version, **data):
            return post(
                viewer,
                "/setup",
                dict(
                    step=step,
                    version=version,
                    scope_workspace=self.ws,
                    action="continue",
                    **data
                ),
            )

        self.assertEqual(go(0, 0).status_code, 302)
        self.assertEqual(go(1, 1).status_code, 302)
        self.assertEqual(
            go(2, 2, profile_action="new", profile_name="Forbidden").status_code, 403
        )
        self.assertEqual(go(2, 2, selected_profile="x" * 32).status_code, 404)
        self.assertEqual(go(2, 2).status_code, 302)
        self.assertEqual(go(3, 3, routine_template="morning").status_code, 403)
        self.assertEqual(
            post(
                viewer,
                "/setup",
                dict(step=3, version=3, scope_workspace=self.ws, action="skip"),
            ).status_code,
            302,
        )

    def test_background_email_rendering_has_no_request_dependency(self):
        from services.account_recovery import request_link
        from olumira.models import User, EmailOutbox

        with self.app.app_context():
            user = db.session.get(User, self.uid)
            user.email_verified = False
            db.session.commit()
            request_link(user.email, "verify_email")
            self.assertIsNotNone(
                db.session.scalar(
                    select(EmailOutbox.id).where(EmailOutbox.user_id == self.uid)
                )
            )
