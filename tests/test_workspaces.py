"""Fictional multi-family regression fixtures; real CSRF and session checks remain on."""

import concurrent.futures
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from flask_migrate import upgrade
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    FamilyWorkspace,
    WorkspaceMembership,
    CareProfile,
    WorkspaceInvitation,
    AuditEvent,
    EmailOutbox,
    Routine,
    Observation,
    RoutineCompletion,
    User,
)
from services.email_delivery import cipher
from services.workspaces import create_workspace
from services.database import transaction
from support import create_user, login, post, csrf_token, PASSWORD


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "APP_ENV": "testing",
                "DATABASE": str(Path(self.temp.name) / "family.db"),
                "AUTH_LOGIN_IP_LIMIT": "1000 per hour",
                "AUTH_LOGIN_ACCOUNT_LIMIT": "1000 per hour",
                "AUTH_REGISTER_LIMIT": "1000 per hour",
            }
        )
        with self.app.app_context():
            upgrade()
        self.owner, self.workspace = create_user(self.app, "owner-fiction@example.com")
        self.other, self.other_workspace = create_user(
            self.app, "other-fiction@example.com"
        )
        self.client = self.app.test_client()
        login(self.client, "owner-fiction@example.com")

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp.cleanup()

    def add_member(self, role="caregiver", email="helper-fiction@example.com"):
        user_id, own_workspace = create_user(self.app, email)
        with self.app.app_context(), transaction():
            member = WorkspaceMembership(
                id="a" * 32,
                workspace_id=self.workspace,
                user_id=user_id,
                role=role,
                status="active",
            )
            db.session.add(member)
        client = self.app.test_client()
        login(client, email)
        response = post(client, "/workspaces/select", {"workspace_id": self.workspace})
        self.assertEqual(response.status_code, 302)
        return client, user_id, "a" * 32

    def profile(self, name="Fictional Fern"):
        response = post(
            self.client,
            "/workspaces/profiles/new",
            {"display_name": name, "avatar": "leaf", "communication": "Short choices"},
        )
        self.assertEqual(response.status_code, 302)
        return response.location.split("/")[-1]

    def invite(self, email="other-fiction@example.com", role="caregiver"):
        self.assertEqual(
            post(
                self.client, "/workspaces/invite", {"email": email, "role": role}
            ).status_code,
            302,
        )
        with self.app.app_context():
            job = db.session.scalar(
                select(EmailOutbox)
                .where(EmailOutbox.kind == "invitation")
                .order_by(EmailOutbox.created_at.desc(), EmailOutbox.id.desc())
            )
            # Choose newest live job, even if issued in same second.
            jobs = list(
                db.session.scalars(
                    select(EmailOutbox).where(
                        EmailOutbox.kind == "invitation",
                        EmailOutbox.cancelled_at.is_(None),
                    )
                )
            )
            job = jobs[-1]
            payload = json.loads(cipher().decrypt(job.encrypted_payload.encode()))
            code = payload["text"].split("#token=")[1].split()[0]
            return code, job.invitation_id, job.id

    def other_client(self):
        client = self.app.test_client()
        login(client, "other-fiction@example.com")
        return client

    def test_workspace_creation_empty_membership_and_switching(self):
        response = post(
            self.client, "/workspaces/create", {"name": "Fictional Cedar Family"}
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as state:
            workspace_id = state["workspace_id"]
        with self.app.app_context():
            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == workspace_id
                )
            )
            self.assertEqual(
                (member.user_id, member.role, member.status),
                (self.owner, "owner", "active"),
            )
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(Routine)
                    .where(Routine.workspace_id == workspace_id)
                ),
                0,
            )
        self.assertNotIn("Brush teeth", self.client.get("/").text)
        post(self.client, "/workspaces/select", {"workspace_id": self.workspace})
        self.assertIn("Brush teeth", self.client.get("/").text)

    def test_invalid_workspace_and_atomic_rollback(self):
        self.assertEqual(
            post(self.client, "/workspaces/create", {"name": " " * 4}).status_code, 422
        )
        self.assertEqual(
            post(self.client, "/workspaces/create", {"name": "x" * 81}).status_code, 422
        )
        with self.app.app_context():
            before = db.session.scalar(
                select(func.count()).select_from(FamilyWorkspace)
            )
            with self.assertRaises(RuntimeError):
                with transaction():
                    create_workspace(self.owner, "Must roll back")
                    raise RuntimeError("fictional failure")
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(FamilyWorkspace)),
                before,
            )

    def test_forged_selection_and_cookie_context(self):
        for workspace_id in [self.other_workspace, "missing", "x" * 500, ""]:
            self.assertEqual(
                post(
                    self.client, "/workspaces/select", {"workspace_id": workspace_id}
                ).status_code,
                404,
            )
        with self.client.session_transaction() as state:
            state["workspace_id"] = self.other_workspace
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as state:
            self.assertEqual(state["workspace_id"], self.workspace)

    def test_duplicate_membership_constraint(self):
        with self.app.app_context(), self.assertRaises(IntegrityError):
            with transaction():
                db.session.add(
                    WorkspaceMembership(
                        id="b" * 32,
                        workspace_id=self.workspace,
                        user_id=self.owner,
                        role="viewer",
                        status="active",
                    )
                )

    def test_settings_owner_only_and_escaping(self):
        client, _, _ = self.add_member("caregiver")
        self.assertEqual(
            post(client, "/workspaces/settings", {"name": "Takeover"}).status_code, 403
        )
        post(
            self.client, "/workspaces/settings", {"name": "<script>fictional</script>"}
        )
        html = self.client.get("/workspaces/settings").text
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>fictional", html)

    def test_cross_workspace_routine_mutations_and_metrics(self):
        with self.app.app_context():
            other_id = db.session.scalar(
                select(Routine.id).where(Routine.workspace_id == self.other_workspace)
            )
        for suffix in ["toggle", "edit", "delete"]:
            self.assertEqual(
                post(
                    self.client,
                    f"/routines/{other_id}/{suffix}",
                    {"name": "Forbidden", "category": "Test"},
                ).status_code,
                404,
            )
        post(
            self.client, "/routines/add", {"name": "Only Cedar", "category": "Fiction"}
        )
        other = self.other_client()
        self.assertNotIn("Only Cedar", other.get("/").text)
        self.assertIn("Only Cedar", self.client.get("/").text)

    def test_profiles_validation_edit_and_foreign_ids(self):
        profile_id = self.profile()
        self.assertEqual(
            self.client.get("/workspaces/profiles/" + profile_id).status_code, 200
        )
        self.assertEqual(
            post(
                self.client,
                "/workspaces/profiles/" + profile_id + "/edit",
                {"display_name": "Fictional Moss", "avatar": "sun"},
            ).status_code,
            302,
        )
        self.assertIn(
            "Fictional Moss", self.client.get("/workspaces/profiles/" + profile_id).text
        )
        other = self.other_client()
        self.assertEqual(
            other.get("/workspaces/profiles/" + profile_id).status_code, 404
        )
        self.assertEqual(
            post(
                other, "/workspaces/profiles/select", {"profile_id": profile_id}
            ).status_code,
            404,
        )
        self.assertEqual(
            post(
                other,
                "/workspaces/profiles/" + profile_id + "/edit",
                {"display_name": "Forbidden"},
            ).status_code,
            404,
        )
        for values in [
            {"display_name": ""},
            {"display_name": "Valid", "avatar": "../../file"},
            {"display_name": "Valid", "support_notes": "x" * 1001},
        ]:
            self.assertEqual(
                post(self.client, "/workspaces/profiles/new", values).status_code, 422
            )

    def test_profile_content_scoping_and_switch_reset(self):
        profile_id = self.profile()
        post(self.client, "/routines/add", {"name": "Fern routine", "category": "Test"})
        post(
            self.client,
            "/observations",
            {
                "activity": "Fern observation",
                "date": "2026-10-17",
                "notes": "Fictional",
            },
        )
        with self.app.app_context():
            routine_id = db.session.scalar(
                select(Routine.id).where(Routine.profile_id == profile_id)
            )
            observation_id = db.session.scalar(
                select(Observation.id).where(Observation.profile_id == profile_id)
            )
        second = self.profile("Fictional Willow")
        self.assertNotIn("Fern routine", self.client.get("/routines").text)
        self.assertNotIn("Fern observation", self.client.get("/observations").text)
        self.assertEqual(
            post(self.client, f"/routines/{routine_id}/toggle").status_code, 404
        )
        self.assertEqual(
            post(
                self.client,
                f"/observations/{observation_id}/edit",
                {"activity": "Forbidden", "date": "2026-10-17"},
            ).status_code,
            404,
        )
        post(self.client, "/workspaces/profiles/select", {"profile_id": profile_id})
        self.assertIn("Fern routine", self.client.get("/").text)
        self.assertIn("Short choices", self.client.get("/communication").text)
        post(self.client, "/workspaces/select", {"workspace_id": self.workspace})
        self.assertNotIn("Fern routine", self.client.get("/").text)

    def test_database_rejects_cross_workspace_profile(self):
        profile_id = self.profile()
        with self.app.app_context(), self.assertRaises(IntegrityError):
            with transaction():
                db.session.add(
                    Routine(
                        owner_id=self.other_workspace,
                        workspace_id=self.other_workspace,
                        profile_id=profile_id,
                        name="Forbidden",
                        category="Test",
                    )
                )

    def test_viewer_all_direct_write_paths_denied(self):
        viewer, _, _ = self.add_member("viewer")
        with self.app.app_context():
            routine_id = db.session.scalar(
                select(Routine.id).where(Routine.workspace_id == self.workspace)
            )
        endpoints = [
            ("/routines/add", {"name": "Forbidden"}),
            ("/routines/add-template", {"template": "Meals"}),
            (f"/routines/{routine_id}/toggle", {}),
            (f"/routines/{routine_id}/edit", {"name": "Forbidden"}),
            (f"/routines/{routine_id}/delete", {}),
            ("/observations", {"activity": "Forbidden"}),
            ("/workspaces/profiles/new", {"display_name": "Forbidden"}),
            ("/workspaces/invite", {"email": "someone@example.com", "role": "owner"}),
            ("/workspaces/settings", {"name": "Forbidden"}),
        ]
        for endpoint, values in endpoints:
            self.assertEqual(post(viewer, endpoint, values).status_code, 403, endpoint)
        self.assertNotIn("Add a routine", viewer.get("/routines").text)
        self.assertNotIn("Save observation", viewer.get("/observations").text)
        self.assertIn("Read-only access", viewer.get("/").text)
        self.assertIn("hidden disabled", viewer.get("/communication/quick").text)

    def test_caregiver_can_edit_content_not_admin(self):
        client, _, _ = self.add_member()
        self.assertEqual(
            post(
                client, "/routines/add", {"name": "Shared walk", "category": "Fiction"}
            ).status_code,
            302,
        )
        self.assertIn("Shared walk", self.client.get("/routines").text)
        self.assertEqual(
            post(
                client,
                "/workspaces/profiles/new",
                {"display_name": "Fictional shared", "avatar": "leaf"},
            ).status_code,
            302,
        )
        for endpoint in [
            "/workspaces/invite",
            "/workspaces/settings",
            "/workspaces/members/" + ("a" * 32) + "/remove",
        ]:
            self.assertEqual(
                post(
                    client,
                    endpoint,
                    {
                        "email": "someone@example.com",
                        "role": "owner",
                        "name": "Forbidden",
                    },
                ).status_code,
                403,
            )

    def test_role_change_removal_active_sessions_and_owner_protection(self):
        client, _, member_id = self.add_member()
        post(self.client, f"/workspaces/members/{member_id}/role", {"role": "viewer"})
        self.assertEqual(
            post(client, "/routines/add", {"name": "Forbidden"}).status_code, 403
        )
        post(self.client, f"/workspaces/members/{member_id}/role", {"role": "owner"})
        with self.app.app_context():
            self.assertEqual(
                db.session.get(WorkspaceMembership, member_id).role, "viewer"
            )
        post(self.client, f"/workspaces/members/{member_id}/remove")
        self.assertEqual(
            post(
                client, "/workspaces/select", {"workspace_id": self.workspace}
            ).status_code,
            404,
        )
        with self.app.app_context():
            owner_id = db.session.scalar(
                select(WorkspaceMembership.id).where(
                    WorkspaceMembership.workspace_id == self.workspace,
                    WorkspaceMembership.user_id == self.owner,
                )
            )
        for action in ["remove", "role"]:
            post(
                self.client,
                f"/workspaces/members/{owner_id}/{action}",
                {"role": "viewer"},
            )
        with self.app.app_context():
            self.assertEqual(
                db.session.get(WorkspaceMembership, owner_id).role, "owner"
            )

    def test_invitation_encrypted_delivery_accept_and_reuse(self):
        code, invitation_id, job_id = self.invite()
        with self.app.app_context():
            invitation = db.session.get(WorkspaceInvitation, invitation_id)
            job = db.session.get(EmailOutbox, job_id)
            self.assertNotIn(code, job.encrypted_payload)
            self.assertEqual(
                invitation.token_hash, hashlib.sha256(code.encode()).hexdigest()
            )
            self.assertNotIn(code, self.client.get("/workspaces/settings").text)
        client = self.other_client()
        self.assertEqual(client.get("/workspaces/accept").status_code, 200)
        with self.app.app_context():
            self.assertIsNone(
                db.session.get(WorkspaceInvitation, invitation_id).accepted_at
            )
        self.assertEqual(
            post(client, "/workspaces/accept", {"recovery_code": code}).status_code, 302
        )
        self.assertEqual(
            post(client, "/workspaces/accept", {"recovery_code": code}).status_code, 410
        )
        with self.app.app_context():
            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.user_id == self.other,
                    WorkspaceMembership.workspace_id == self.workspace,
                )
            )
            self.assertEqual(member.role, "caregiver")
            self.assertIsNotNone(db.session.get(EmailOutbox, job_id).cancelled_at)

    def test_invitation_mismatch_expired_revoked_and_invalid(self):
        code, invitation_id, _ = self.invite()
        self.assertEqual(
            post(
                self.client, "/workspaces/accept", {"recovery_code": code}
            ).status_code,
            410,
        )
        other = self.other_client()
        with self.app.app_context(), transaction():
            db.session.get(WorkspaceInvitation, invitation_id).expires_at = (
                int(time.time()) - 1
            )
        self.assertEqual(
            post(other, "/workspaces/accept", {"recovery_code": code}).status_code, 410
        )
        code, invitation_id, _ = self.invite()
        post(self.client, f"/workspaces/invitations/{invitation_id}/revoke")
        self.assertEqual(
            post(other, "/workspaces/accept", {"recovery_code": code}).status_code, 410
        )
        self.assertEqual(
            post(other, "/workspaces/accept", {"recovery_code": "x" * 43}).status_code,
            410,
        )
        self.assertEqual(
            post(other, "/workspaces/accept", {"recovery_code": "bad"}).status_code, 422
        )

    def test_rotation_and_duplicate_invitation_membership(self):
        old, old_id, old_job = self.invite()
        self.assertEqual(
            post(self.client, f"/workspaces/invitations/{old_id}/resend").status_code,
            302,
        )
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(WorkspaceInvitation, old_id).revoked_at)
            self.assertIsNotNone(db.session.get(EmailOutbox, old_job).cancelled_at)
            pending = list(
                db.session.scalars(
                    select(WorkspaceInvitation).where(
                        WorkspaceInvitation.revoked_at.is_(None)
                    )
                )
            )
            self.assertEqual(len(pending), 1)
        self.assertEqual(
            post(
                self.other_client(), "/workspaces/accept", {"recovery_code": old}
            ).status_code,
            410,
        )
        self.assertEqual(
            post(
                self.client, "/workspaces/invite", {"email": "invalid", "role": "owner"}
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(
                    select(func.count()).select_from(WorkspaceInvitation)
                ),
                2,
            )

    def test_new_account_invitation_and_unverified_gate(self):
        code, _, _ = self.invite("new-fiction@example.com", "viewer")
        anonymous = self.app.test_client()
        self.assertIn("Create account", anonymous.get("/workspaces/accept").text)
        user_id, _ = create_user(self.app, "new-fiction@example.com")
        with self.app.app_context(), transaction():
            db.session.get(User, user_id).email_verified = False
        login(anonymous, "new-fiction@example.com")
        self.assertEqual(
            post(anonymous, "/workspaces/accept", {"recovery_code": code}).status_code,
            403,
        )
        with self.app.app_context(), transaction():
            db.session.get(User, user_id).email_verified = True
        self.assertEqual(
            post(anonymous, "/workspaces/accept", {"recovery_code": code}).status_code,
            302,
        )

    def test_invitation_queue_failure_rolls_back(self):
        with patch(
            "services.collaboration.cipher",
            side_effect=RuntimeError("fictional queue unavailable"),
        ):
            self.assertEqual(
                post(
                    self.client,
                    "/workspaces/invite",
                    {"email": "other-fiction@example.com", "role": "viewer"},
                ).status_code,
                503,
            )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(
                    select(func.count()).select_from(WorkspaceInvitation)
                ),
                0,
            )

    def test_invitation_authorization_and_foreign_management(self):
        code, invitation_id, _ = self.invite()
        other = self.other_client()
        for action in ["revoke", "resend"]:
            self.assertEqual(
                post(
                    other, f"/workspaces/invitations/{invitation_id}/{action}"
                ).status_code,
                404,
            )
        with self.app.app_context():
            member_id = db.session.scalar(
                select(WorkspaceMembership.id).where(
                    WorkspaceMembership.workspace_id == self.workspace,
                    WorkspaceMembership.user_id == self.owner,
                )
            )
        self.assertEqual(
            post(other, f"/workspaces/members/{member_id}/remove").status_code, 302
        )
        with self.app.app_context():
            self.assertEqual(
                db.session.get(WorkspaceMembership, member_id).status, "active"
            )

    def test_concurrent_acceptance_exactly_one_membership(self):
        code, _, _ = self.invite()
        first = self.other_client()
        second = self.other_client()
        first_token = csrf_token(first)
        second_token = csrf_token(second)

        def accept(pair):
            client, token = pair
            return client.post(
                "/workspaces/accept", data={"csrf_token": token, "recovery_code": code}
            ).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(
                pool.map(accept, [(first, first_token), (second, second_token)])
            )
        self.assertEqual(sorted(statuses), [302, 410])
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(WorkspaceMembership)
                    .where(
                        WorkspaceMembership.workspace_id == self.workspace,
                        WorkspaceMembership.user_id == self.other,
                    )
                ),
                1,
            )

    def test_csrf_all_new_mutations(self):
        profile_id = self.profile()
        code, invitation_id, _ = self.invite()
        endpoints = [
            "/workspaces/create",
            "/workspaces/select",
            "/workspaces/settings",
            "/workspaces/profiles/new",
            "/workspaces/profiles/select",
            "/workspaces/profiles/" + profile_id + "/edit",
            "/workspaces/invite",
            "/workspaces/invitations/" + invitation_id + "/revoke",
            "/workspaces/invitations/" + invitation_id + "/resend",
            "/workspaces/members/" + ("a" * 32) + "/role",
            "/workspaces/members/" + ("a" * 32) + "/remove",
            "/workspaces/accept",
        ]
        for endpoint in endpoints:
            self.assertEqual(
                self.client.post(endpoint, data={}).status_code, 400, endpoint
            )

    def test_invitation_rate_limit(self):
        for _ in range(10):
            self.assertEqual(
                post(
                    self.client,
                    "/workspaces/invite",
                    {"email": "other-fiction@example.com", "role": "viewer"},
                ).status_code,
                302,
            )
        self.assertEqual(
            post(
                self.client,
                "/workspaces/invite",
                {"email": "other-fiction@example.com", "role": "viewer"},
            ).status_code,
            429,
        )

    def test_audit_redaction_immutability_and_private_headers(self):
        profile_id = self.profile()
        post(
            self.client,
            "/observations",
            {
                "activity": "Private fictional activity",
                "date": "2026-10-17",
                "notes": "Private fictional note",
            },
        )
        with self.app.app_context():
            events = list(
                db.session.scalars(
                    select(AuditEvent).where(AuditEvent.workspace_id == self.workspace)
                )
            )
            serialized = repr([(e.event_type, e.actor_id, e.target_id) for e in events])
            self.assertNotIn("Private fictional", serialized)
            self.assertNotIn(PASSWORD, serialized)
            with self.assertRaises(IntegrityError):
                with transaction():
                    db.session.execute(
                        text("UPDATE audit_events SET event_type=:kind"),
                        {"kind": "forged"},
                    )
        for endpoint in [
            "/",
            "/workspaces/settings",
            "/workspaces/profiles/" + profile_id,
        ]:
            response = self.client.get(endpoint)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertIn("noindex", response.headers["X-Robots-Tag"])
            self.assertIn(
                "frame-ancestors 'none'", response.headers["Content-Security-Policy"]
            )

    def test_anonymous_and_unverified_workspace_gates(self):
        anonymous = self.app.test_client()
        for endpoint in [
            "/workspaces/create",
            "/workspaces/invite",
            "/workspaces/select",
            "/workspaces/profiles/new",
        ]:
            response = post(
                anonymous,
                endpoint,
                {
                    "name": "Forbidden",
                    "email": "other-fiction@example.com",
                    "role": "viewer",
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertIn("/auth/login", response.location)
        with self.app.app_context(), transaction():
            db.session.get(User, self.owner).email_verified = False
        self.assertIn("/auth/verification", self.client.get("/workspaces").location)

    def test_viewer_profile_and_observation_edits_denied(self):
        profile_id = self.profile()
        post(
            self.client,
            "/observations",
            {"activity": "Fictional private", "date": "2026-10-17"},
        )
        with self.app.app_context():
            observation_id = db.session.scalar(
                select(Observation.id).where(Observation.workspace_id == self.workspace)
            )
        viewer, _, _ = self.add_member("viewer")
        for endpoint, values in [
            (
                "/workspaces/profiles/" + profile_id + "/edit",
                {"display_name": "Forbidden"},
            ),
            (
                "/observations/" + str(observation_id) + "/edit",
                {"activity": "Forbidden", "date": "2026-10-17"},
            ),
        ]:
            self.assertEqual(post(viewer, endpoint, values).status_code, 403)

    def test_role_changes_and_removals_reject_foreign_ids(self):
        with self.app.app_context():
            foreign = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == self.other_workspace
                )
            )
            foreign_id = foreign.id
        for action in ["role", "remove"]:
            post(
                self.client,
                "/workspaces/members/" + foreign_id + "/" + action,
                {"role": "viewer"},
            )
        with self.app.app_context():
            foreign = db.session.get(WorkspaceMembership, foreign_id)
            self.assertEqual((foreign.role, foreign.status), ("owner", "active"))

    def test_current_email_and_inviter_revocation_invalidate_acceptance(self):
        code, _, _ = self.invite()
        client = self.other_client()
        with self.app.app_context(), transaction():
            db.session.get(User, self.other).email = "changed-fiction@example.com"
        self.assertEqual(
            post(client, "/workspaces/accept", {"recovery_code": code}).status_code, 410
        )
        with self.app.app_context(), transaction():
            db.session.get(User, self.other).email = "other-fiction@example.com"
            owner = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == self.workspace,
                    WorkspaceMembership.user_id == self.owner,
                )
            )
            owner.status = "revoked"
        self.assertEqual(
            post(client, "/workspaces/accept", {"recovery_code": code}).status_code, 410
        )

    def test_invitation_mail_canonical_origin_and_cancelled_delivery(self):
        from services.email_delivery import deliver_pending

        self.app.config["PUBLIC_APP_URL"] = "https://canonical-fiction.example.com"
        code, invitation_id, job_id = self.invite()
        with self.app.app_context():
            job = db.session.get(EmailOutbox, job_id)
            payload = json.loads(cipher().decrypt(job.encrypted_payload.encode()))
            self.assertIn(
                "https://canonical-fiction.example.com/workspaces/accept#token=",
                payload["text"],
            )
            self.assertNotIn("support_notes", payload["text"])
            self.app.config["MAIL_BACKEND"] = "smtp"
            with patch("services.email_delivery.send_smtp") as send:
                counts = deliver_pending()
            self.assertEqual(counts["sent"], 1)
            message = send.call_args.args[0]
            self.assertEqual(message["To"], "other-fiction@example.com")
            self.assertEqual(message.get_content_type(), "multipart/alternative")
            self.app.config["MAIL_BACKEND"] = "development"
        code, invitation_id, job_id = self.invite()
        post(self.client, "/workspaces/invitations/" + invitation_id + "/revoke")
        with self.app.app_context():
            self.app.config["MAIL_BACKEND"] = "smtp"
            with patch("services.email_delivery.send_smtp") as send:
                deliver_pending()
            send.assert_not_called()

    def test_observation_edit_allowed_but_foreign_workspace_denied(self):
        post(
            self.client,
            "/observations",
            {
                "activity": "Fictional original",
                "date": "2026-10-17",
                "notes": "Fictional note",
            },
        )
        with self.app.app_context():
            observation_id = db.session.scalar(
                select(Observation.id).where(Observation.workspace_id == self.workspace)
            )
        endpoint = "/observations/" + str(observation_id) + "/edit"
        values = {
            "activity": "Fictional updated",
            "date": "2026-10-17",
            "notes": "Still fictional",
        }
        self.assertEqual(post(self.other_client(), endpoint, values).status_code, 404)
        self.assertEqual(post(self.client, endpoint, values).status_code, 302)
        self.assertIn("Fictional updated", self.client.get("/observations").text)
        self.assertNotIn("Fictional original", self.client.get("/observations").text)

    def test_caregiver_profile_edit_and_audit_delete_protection(self):
        profile_id = self.profile()
        client, _, _ = self.add_member("caregiver")
        self.assertEqual(
            post(
                client,
                "/workspaces/profiles/" + profile_id + "/edit",
                {"display_name": "Fictional shared nickname", "avatar": "star"},
            ).status_code,
            302,
        )
        self.assertIn(
            "Fictional shared nickname",
            self.client.get("/workspaces/profiles/" + profile_id).text,
        )
        with self.app.app_context():
            for statement in [
                "DELETE FROM audit_events",
                "UPDATE care_profiles SET workspace_id=:workspace",
            ]:
                with self.assertRaises(IntegrityError):
                    with transaction():
                        db.session.execute(
                            text(statement), {"workspace": self.other_workspace}
                        )
