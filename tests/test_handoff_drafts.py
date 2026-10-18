"""Drafts never enter shared history before an explicit reviewed share."""

import uuid
from datetime import datetime, timezone
import unittest
import test_communication as fixtures
from support import post
from olumira.extensions import db
from olumira.models import (
    HandoffDraft,
    CaregiverHandoff,
    Observation,
    RoutineSession,
    WorkspaceMembership,
)
from sqlalchemy import select, func


class HandoffDraftTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def values(self, **changes):
        values = dict(
            scope_workspace=self.ws,
            profile_id="",
            recipient=self.other,
            start="2030-01-01T08:00",
            end="2030-01-01T16:00",
            state="draft",
            summary="Fictional reviewed shift",
            version="",
            creation_key=uuid.uuid4().hex,
            studio_action="save",
        )
        values.update(changes)
        return values

    def test_generation_explicit_observations_time_privacy_and_share(self):
        helper = self.shared("caregiver")
        with self.app.app_context():
            selected = Observation(
                workspace_id=self.ws,
                profile_id=None,
                activity="Selected choice",
                notes="Chosen note",
                date="2030-01-01",
                observed_at=datetime(2030, 1, 1, 16, tzinfo=timezone.utc),
            )
            hidden = Observation(
                workspace_id=self.ws,
                profile_id=None,
                activity="UNSELECTED SECRET",
                notes="DO NOT COPY",
                date="2030-01-01",
                observed_at=datetime(2030, 1, 1, 16, tzinfo=timezone.utc),
            )
            db.session.add_all([selected, hidden])
            db.session.commit()
            oid = selected.id
        response = post(
            self.client,
            "/care/handoffs/studio",
            self.values(
                studio_action="generate",
                categories=["observations"],
                observation_ids=[str(oid)],
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        # Other authorized choices can appear in the selector, but never in the generated editor/preview.
        import html, re

        summary = html.unescape(
            re.search(
                r'<textarea[^>]*id="draft-summary"[^>]*>(.*?)</textarea>',
                response.text,
                re.S,
            ).group(1)
        )
        self.assertIn("Chosen note", summary)
        self.assertNotIn("UNSELECTED SECRET", summary)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(HandoffDraft)), 0
            )
        saved = post(self.client, "/care/handoffs/studio", self.values(summary=summary))
        self.assertEqual(saved.status_code, 302, saved.text)
        url = saved.location
        identity = url.rsplit("/", 1)[1]
        self.assertEqual(helper.get(url).status_code, 404)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(CaregiverHandoff)), 0
            )
        self.assertEqual(
            post(
                self.client,
                url + "/share",
                dict(scope_workspace=self.ws, version=1, confirm="share"),
            ).status_code,
            409,
        )
        self.assertEqual(
            post(
                self.client, url, self.values(summary=summary, state="ready", version=1)
            ).status_code,
            302,
        )
        shared = post(
            self.client,
            url + "/share",
            dict(scope_workspace=self.ws, version=2, confirm="share"),
        )
        self.assertEqual(shared.status_code, 302, shared.text)
        self.assertEqual(
            post(
                self.client,
                url + "/share",
                dict(scope_workspace=self.ws, version=2, confirm="share"),
            ).location,
            shared.location,
        )
        self.assertEqual(helper.get(shared.location).status_code, 200)
        self.assertEqual(
            post(
                helper, shared.location + "/acknowledge", dict(scope_workspace=self.ws)
            ).status_code,
            302,
        )
        self.assertEqual(
            post(self.client, url, self.values(state="ready", version=3)).status_code,
            422,
        )

    def test_invalid_time_recipient_foreign_scope_and_stale_version(self):
        self.shared("caregiver")
        for changes in [
            dict(start="bad"),
            dict(end="2030-02-01T16:00"),
            dict(recipient=self.uid),
        ]:
            self.assertEqual(
                post(
                    self.client, "/care/handoffs/studio", self.values(**changes)
                ).status_code,
                422,
            )
        saved = post(self.client, "/care/handoffs/studio", self.values())
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(
            post(self.client, saved.location, self.values(version=9)).status_code, 409
        )
        with self.app.app_context():
            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == self.ws,
                    WorkspaceMembership.user_id == self.other,
                )
            )
            member.status = "revoked"
            db.session.commit()
        self.assertEqual(
            post(
                self.client, saved.location, self.values(version=1, state="ready")
            ).status_code,
            422,
        )

    def test_completed_routine_and_task_summary_time_window(self):
        import test_routine_builder as routines
        import test_care_coordination as tasks

        self.shared("caregiver")
        created = post(
            self.client, "/routines/new", routines.RoutineBuilderTests.values(self)
        )
        self.assertEqual(created.status_code, 302)
        started = post(
            self.client, created.location + "/start", dict(launch_key=uuid.uuid4().hex)
        )
        sid = started.location.split("/sessions/")[1].split("?")[0]
        with self.app.app_context():
            run = db.session.get(RoutineSession, sid)
            run.status = "completed"
            run.active_key = None
            run.completed_at = datetime(2030, 1, 1, 16, tzinfo=timezone.utc)
            db.session.commit()
        task = post(
            self.client, "/care/tasks/new", tasks.CareCoordinationTests.values(self)
        )
        self.assertEqual(task.status_code, 302)
        values = self.values(
            studio_action="generate", categories=["completed", "tasks"]
        )
        response = post(self.client, "/care/handoffs/studio", values)
        self.assertEqual(response.status_code, 200, response.text)
        import html, re

        summary = html.unescape(
            re.search(
                r'<textarea[^>]*id="draft-summary"[^>]*>(.*?)</textarea>',
                response.text,
                re.S,
            ).group(1)
        )
        self.assertIn("Fictional gentle morning", summary)
        self.assertIn("Fictional prepare story cards", summary)
        values.update(start="2030-01-02T08:00", end="2030-01-02T16:00")
        response = post(self.client, "/care/handoffs/studio", values)
        summary = html.unescape(
            re.search(
                r'<textarea[^>]*id="draft-summary"[^>]*>(.*?)</textarea>',
                response.text,
                re.S,
            ).group(1)
        )
        self.assertNotIn("Fictional gentle morning", summary)

    def test_private_draft_export_and_account_closure(self):
        import json, re
        from support import PASSWORD

        self.shared("caregiver")
        saved = post(
            self.client,
            "/care/handoffs/studio",
            self.values(summary="Private fictional draft export marker"),
        )
        self.assertEqual(saved.status_code, 302)
        identity = saved.location.rsplit("/", 1)[1]
        request_values = dict(
            action="export",
            scope="personal",
            scope_workspace=self.ws,
            current_password=PASSWORD,
        )
        response = post(self.client, "/settings/privacy", request_values)
        token = re.search(
            r'name="download_token" value="([^"]+)"', response.text
        ).group(1)
        exported = post(
            self.client, "/settings/privacy/download", dict(download_token=token)
        )
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertEqual(
            json.loads(exported.data)["records"]["handoff_drafts"][0]["summary"],
            "Private fictional draft export marker",
        )
        request_values["scope"] = "workspace"
        response = post(self.client, "/settings/privacy", request_values)
        token = re.search(
            r'name="download_token" value="([^"]+)"', response.text
        ).group(1)
        exported = post(
            self.client, "/settings/privacy/download", dict(download_token=token)
        )
        self.assertEqual(exported.status_code, 200)
        self.assertNotIn("Private fictional draft export marker", exported.text)
        transfer = dict(
            action="transfer",
            scope_workspace=self.ws,
            current_password=PASSWORD,
            successor=self.other,
        )
        self.assertEqual(
            post(self.client, "/settings/privacy", transfer).status_code, 302
        )
        self.assertEqual(
            post(
                self.client,
                "/settings/privacy",
                dict(
                    action="account",
                    scope_workspace=self.ws,
                    current_password=PASSWORD,
                    confirm="DELETE MY ACCOUNT",
                ),
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertIsNone(db.session.get(HandoffDraft, identity))
