"""Day 22 builder, persistence, negative authorization and conflict regressions."""

import concurrent.futures
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from flask_migrate import upgrade
from sqlalchemy import select, func
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    Routine,
    RoutineStep,
    RoutineCompletion,
    RoutineCompletionSnapshot,
    CareProfile,
    WorkspaceMembership,
    AuditEvent,
)
from services.routine_builder import draft
from support import create_user, login, post, csrf_token


class RoutineBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "APP_ENV": "testing",
                "DATABASE": str(Path(self.temp.name) / "builder.db"),
                "AUTH_LOGIN_IP_LIMIT": "1000 per hour",
                "AUTH_LOGIN_ACCOUNT_LIMIT": "1000 per hour",
            }
        )
        with self.app.app_context():
            upgrade()
        self.user, self.workspace = create_user(
            self.app, "fictional-builder@example.com"
        )
        self.other, self.other_workspace = create_user(
            self.app, "fictional-other-builder@example.com"
        )
        self.client = self.app.test_client()
        login(self.client, "fictional-builder@example.com")

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp.cleanup()

    def values(self, **changes):
        values = dict(
            name="Fictional gentle morning",
            description="Fictional demonstration only.",
            category="Morning",
            icon="sun",
            color="sage",
            profile_id="",
            version="",
            step_id=["", "", ""],
            step_title=["Choose clothes", "Share breakfast", "Read a story"],
            step_description=["A familiar choice.", "", "Take your time."],
            step_icon=["person", "sun", "book"],
        )
        values.update(changes)
        return values

    def create(self, **changes):
        response = post(self.client, "/routines/new", self.values(**changes))
        self.assertEqual(response.status_code, 302, response.text)
        return int(response.location.rsplit("/", 1)[1])

    def edit_values(self, routine_id, **changes):
        with self.app.app_context():
            values = draft(db.session.get(Routine, routine_id))
        steps = values.pop("steps")
        for key, field in [
            ("id", "step_id"),
            ("title", "step_title"),
            ("description", "step_description"),
            ("icon", "step_icon"),
        ]:
            values[field] = [step[key] for step in steps]
        values.update(changes)
        return values

    def test_create_metadata_steps_preview_and_real_dashboard_definition(self):
        routine_id = self.create()
        with self.app.app_context():
            routine = db.session.get(Routine, routine_id)
            steps = list(
                db.session.scalars(
                    select(RoutineStep)
                    .where(RoutineStep.routine_id == routine_id)
                    .order_by(RoutineStep.position)
                )
            )
            self.assertEqual(routine.workspace_id, self.workspace)
            self.assertFalse(routine.is_checklist)
            self.assertEqual(routine.created_by, self.user)
            self.assertEqual(
                [(s.title, s.position) for s in steps],
                [("Choose clothes", 0), ("Share breakfast", 1), ("Read a story", 2)],
            )
        self.assertIn(
            "Read a story", self.client.get("/routines/" + str(routine_id)).text
        )
        self.assertIn("Fictional gentle morning", self.client.get("/").text)
        self.assertEqual(
            post(self.client, "/routines/" + str(routine_id) + "/toggle").status_code,
            404,
        )

    def test_edit_reorder_insert_remove_preserves_ids(self):
        routine_id = self.create()
        values = self.edit_values(routine_id)
        original = values["step_id"][:]
        for field in ["step_id", "step_title", "step_description", "step_icon"]:
            values[field] = values[field][::-1]
        values["step_id"][1] = ""
        values["step_title"][1] = "A new fictional step"
        self.assertEqual(
            post(self.client, f"/routines/{routine_id}/builder", values).status_code,
            302,
        )
        with self.app.app_context():
            rows = list(
                db.session.scalars(
                    select(RoutineStep)
                    .where(RoutineStep.routine_id == routine_id)
                    .order_by(RoutineStep.position)
                )
            )
            self.assertEqual([s.position for s in rows], [0, 1, 2])
            self.assertEqual(rows[0].id, original[2])
            self.assertEqual(rows[2].id, original[0])
            self.assertIsNone(db.session.get(RoutineStep, original[1]))
            self.assertEqual(db.session.get(Routine, routine_id).version, 2)

    def test_stale_version_keeps_draft_and_does_not_overwrite(self):
        routine_id = self.create()
        first = self.edit_values(routine_id)
        second = dict(first)
        first["name"] = "Fictional first editor"
        self.assertEqual(
            post(self.client, f"/routines/{routine_id}/builder", first).status_code, 302
        )
        second["name"] = "Fictional unsaved draft"
        response = post(self.client, f"/routines/{routine_id}/builder", second)
        self.assertEqual(response.status_code, 409)
        self.assertIn("Fictional unsaved draft", response.text)
        self.assertIn("Open latest saved version", response.text)
        with self.app.app_context():
            self.assertEqual(
                db.session.get(Routine, routine_id).name, "Fictional first editor"
            )

    def test_duplicate_does_not_copy_completion_and_can_target_authorized_profile(self):
        routine_id = self.create()
        profile_id = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id=profile_id,
                    workspace_id=self.workspace,
                    display_name="Fictional Fern",
                )
            )
            db.session.commit()
        response = post(
            self.client, f"/routines/{routine_id}/duplicate", {"profile_id": profile_id}
        )
        self.assertEqual(response.status_code, 302)
        copied_id = int(response.location.split("/")[-2])
        with self.app.app_context():
            copied = db.session.get(Routine, copied_id)
            self.assertEqual(copied.profile_id, profile_id)
            self.assertTrue(copied.name.endswith("(copy)"))
            source_steps = list(
                db.session.scalars(
                    select(RoutineStep).where(RoutineStep.routine_id == routine_id)
                )
            )
            copy_steps = list(
                db.session.scalars(
                    select(RoutineStep).where(RoutineStep.routine_id == copied_id)
                )
            )
            self.assertEqual(len(copy_steps), 3)
            self.assertFalse({s.id for s in source_steps} & {s.id for s in copy_steps})
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(RoutineCompletion)
                    .where(RoutineCompletion.routine_id == copied_id)
                ),
                0,
            )

    def test_archive_restore_and_legacy_delete_keep_completion_snapshot(self):
        with self.app.app_context():
            routine_id = db.session.scalar(
                select(Routine.id).where(Routine.workspace_id == self.workspace)
            )
        post(self.client, f"/routines/{routine_id}/toggle")
        self.assertEqual(
            post(
                self.client, f"/routines/{routine_id}/delete", {"version": "1"}
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Routine, routine_id).archived_at)
            self.assertIsNotNone(
                db.session.scalar(
                    select(RoutineCompletion).where(
                        RoutineCompletion.routine_id == routine_id
                    )
                )
            )
            snapshot = db.session.scalar(
                select(RoutineCompletionSnapshot).where(
                    RoutineCompletionSnapshot.routine_id == routine_id
                )
            )
            self.assertEqual(snapshot.source, "completion")
        self.assertEqual(
            post(self.client, f"/routines/{routine_id}/toggle").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/routines/{routine_id}/builder").status_code, 409
        )
        self.assertEqual(
            post(
                self.client, f"/routines/{routine_id}/restore", {"version": "2"}
            ).status_code,
            302,
        )
        self.assertIn("Wake up", self.client.get("/routines").text)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Routine, routine_id).archived_at)

    def test_archive_stale_version_denied(self):
        routine_id = self.create()
        self.assertEqual(
            post(
                self.client, f"/routines/{routine_id}/archive", {"version": "0"}
            ).status_code,
            409,
        )
        self.assertEqual(
            post(
                self.client, f"/routines/{routine_id}/archive", {"version": "1"}
            ).status_code,
            302,
        )
        self.assertEqual(
            post(
                self.client, f"/routines/{routine_id}/restore", {"version": "1"}
            ).status_code,
            409,
        )

    def test_historical_label_survives_legacy_rename(self):
        with self.app.app_context():
            routine_id = db.session.scalar(
                select(Routine.id).where(Routine.workspace_id == self.workspace)
            )
        post(self.client, f"/routines/{routine_id}/toggle")
        self.assertEqual(
            post(
                self.client,
                f"/routines/{routine_id}/edit",
                {
                    "name": "Fictional changed label",
                    "category": "Morning",
                    "version": "1",
                },
            ).status_code,
            302,
        )
        with self.app.app_context():
            snapshot = db.session.scalar(
                select(RoutineCompletionSnapshot).where(
                    RoutineCompletionSnapshot.routine_id == routine_id
                )
            )
            self.assertEqual(snapshot.name, "Wake up")
            self.assertEqual(
                db.session.get(Routine, routine_id).name, "Fictional changed label"
            )
        self.assertEqual(
            post(
                self.client,
                f"/routines/{routine_id}/edit",
                {"name": "Stale", "category": "Morning", "version": "1"},
            ).status_code,
            409,
        )

    def test_invalid_input_ids_and_no_partial_writes(self):
        cases = [
            {"name": ""},
            {"name": "x" * 81},
            {"description": "x" * 1001},
            {"category": "x" * 41},
            {"color": "red;display:none"},
            {"icon": "<script>"},
            {"step_title": ["", "Valid", "Valid"]},
            {"step_description": ["x" * 501, "", ""]},
            {"step_icon": ["not-an-icon", "sun", "book"]},
            {"step_id": ["x", "x", ""]},
            {"step_title": ["Valid"]},
            {"step_id": [], "step_title": [], "step_description": [], "step_icon": []},
        ]
        with self.app.app_context():
            before = db.session.scalar(select(func.count()).select_from(Routine))
        for changes in cases:
            self.assertEqual(
                post(self.client, "/routines/new", self.values(**changes)).status_code,
                422,
                changes.keys(),
            )
        self.assertEqual(
            post(
                self.client, "/routines/new", self.values(step_id=["foreign", "", ""])
            ).status_code,
            404,
        )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Routine)), before
            )

    def test_foreign_steps_workspace_profile_and_old_endpoint_bypasses(self):
        first = self.create()
        second = self.create(name="Fictional second sequence")
        values = self.edit_values(first)
        with self.app.app_context():
            foreign_step = db.session.scalar(
                select(RoutineStep.id).where(RoutineStep.routine_id == second)
            )
            foreign_profile = CareProfile(
                id=uuid.uuid4().hex,
                workspace_id=self.other_workspace,
                display_name="Fictional separate profile",
            )
            db.session.add(foreign_profile)
            db.session.commit()
            profile_id = foreign_profile.id
        values["step_id"][0] = foreign_step
        self.assertEqual(
            post(self.client, f"/routines/{first}/builder", values).status_code, 404
        )
        self.assertEqual(
            post(
                self.client, "/routines/new", self.values(profile_id=profile_id)
            ).status_code,
            404,
        )
        self.assertEqual(
            post(
                self.client, f"/routines/{first}/duplicate", {"profile_id": profile_id}
            ).status_code,
            404,
        )
        self.assertEqual(
            post(
                self.client,
                f"/routines/{first}/edit",
                {"name": "Forbidden", "category": "Morning", "version": "1"},
            ).status_code,
            404,
        )
        other = self.app.test_client()
        login(other, "fictional-other-builder@example.com")
        for endpoint in [f"/routines/{first}", f"/routines/{first}/builder"]:
            self.assertEqual(other.get(endpoint).status_code, 404)
        for suffix in ["builder", "duplicate", "archive", "restore"]:
            self.assertEqual(
                post(
                    other, f"/routines/{first}/{suffix}", self.values(version="1")
                ).status_code,
                404,
            )

    def test_viewer_read_only_and_caregiver_writes(self):
        routine_id = self.create()
        member_id = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add(
                WorkspaceMembership(
                    id=member_id,
                    workspace_id=self.workspace,
                    user_id=self.other,
                    role="viewer",
                    status="active",
                )
            )
            db.session.commit()
        client = self.app.test_client()
        login(client, "fictional-other-builder@example.com")
        post(client, "/workspaces/select", {"workspace_id": self.workspace})
        self.assertEqual(client.get(f"/routines/{routine_id}").status_code, 200)
        for endpoint in [
            "/routines/new",
            f"/routines/{routine_id}/builder",
            f"/routines/{routine_id}/duplicate",
            f"/routines/{routine_id}/archive",
            f"/routines/{routine_id}/restore",
        ]:
            self.assertEqual(
                post(client, endpoint, self.values(version="1")).status_code, 403
            )
        with self.app.app_context():
            db.session.get(WorkspaceMembership, member_id).role = "caregiver"
            db.session.commit()
        self.assertEqual(
            post(
                client, "/routines/new", self.values(name="Fictional shared creation")
            ).status_code,
            302,
        )

    def test_csrf_and_draft_controls_do_not_save(self):
        routine_id = self.create()
        for endpoint in [
            "/routines/new",
            f"/routines/{routine_id}/builder",
            f"/routines/{routine_id}/duplicate",
            f"/routines/{routine_id}/archive",
            f"/routines/{routine_id}/restore",
        ]:
            self.assertEqual(
                self.client.post(endpoint, data=self.values()).status_code, 400
            )
        with self.app.app_context():
            before = db.session.scalar(select(func.count()).select_from(Routine))
        response = post(self.client, "/routines/new", self.values(builder_action="add"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.text.split("<template")[0].count("data-step-editor>"), 4
        )
        response = post(
            self.client, "/routines/new", self.values(builder_action="up:2")
        )
        self.assertEqual(response.status_code, 200)
        self.assertLess(
            response.text.index('value="Read a story"'),
            response.text.index('value="Share breakfast"'),
        )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(Routine)), before
            )

    def test_search_category_archived_filters_and_escaping(self):
        routine_id = self.create(name="<script>Fictional</script>")
        self.assertIn(
            "&lt;script&gt;Fictional", self.client.get("/routines?q=Fictional").text
        )
        self.assertNotIn(
            "<script>Fictional", self.client.get("/routines?q=Fictional").text
        )
        self.assertNotIn(
            "Fictional gentle morning", self.client.get("/routines?q=missing").text
        )
        post(self.client, f"/routines/{routine_id}/archive", {"version": "1"})
        self.assertNotIn("&lt;script&gt;Fictional", self.client.get("/routines").text)
        self.assertIn(
            "&lt;script&gt;Fictional", self.client.get("/routines?status=archived").text
        )
        for query in ["?page=-1", "?page=bad", "?status=invalid", "?q=" + ("x" * 101)]:
            self.assertEqual(self.client.get("/routines" + query).status_code, 400)
        self.assertNotIn(
            "&lt;script&gt;Fictional",
            self.client.get("/routines?status=all&q=%25").text,
        )

    def test_template_drafts_are_copied_not_globally_changed(self):
        response = self.client.get("/routines/new?template=morning")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Check the day ahead", response.text)
        self.assertEqual(
            self.client.get("/routines/new?template=unknown").status_code, 404
        )
        self.create(name="Fictional customized template")
        self.assertNotIn(
            "Fictional customized template",
            self.client.get("/routines/new?template=morning").text,
        )

    def test_forced_failure_rolls_back_metadata_and_steps(self):
        routine_id = self.create()
        values = self.edit_values(routine_id, name="Fictional failed save")
        with patch(
            "services.routine_builder.care_audit",
            side_effect=RuntimeError("Fictional failure"),
        ):
            with self.assertRaises(RuntimeError):
                post(self.client, f"/routines/{routine_id}/builder", values)
        with self.app.app_context():
            self.assertEqual(
                db.session.get(Routine, routine_id).name, "Fictional gentle morning"
            )
            self.assertEqual(db.session.get(Routine, routine_id).version, 1)
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(RoutineStep)
                    .where(RoutineStep.routine_id == routine_id)
                ),
                3,
            )

    def test_concurrent_edit_conflict_preserves_winner(self):
        routine_id = self.create()
        values = self.edit_values(routine_id)
        second = self.app.test_client()
        login(second, "fictional-builder@example.com")
        tokens = [csrf_token(self.client), csrf_token(second)]

        def save(pair):
            index, client = pair
            payload = dict(
                values, name="Fictional editor " + str(index), csrf_token=tokens[index]
            )
            return client.post(
                f"/routines/{routine_id}/builder", data=payload
            ).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, enumerate([self.client, second])))
        self.assertEqual(sorted(results), [302, 409])
        with self.app.app_context():
            self.assertEqual(db.session.get(Routine, routine_id).version, 2)

    def test_maximum_unicode_form_and_oversized_request_limit(self):
        values = self.values(
            name="Fictional Unicode routine",
            description="🌿" * 1000,
            step_id=[""] * 30,
            step_title=["🌿" * 80] * 30,
            step_description=["🌿" * 500] * 30,
            step_icon=["leaf"] * 30,
        )
        self.assertEqual(post(self.client, "/routines/new", values).status_code, 302)
        token = csrf_token(self.client)
        self.assertEqual(
            self.client.post(
                "/routines/new", data={"csrf_token": token, "extra": "x" * (270 * 1024)}
            ).status_code,
            413,
        )
        self.assertEqual(
            self.client.post(
                "/auth/login", data={"csrf_token": token, "extra": "x" * (65 * 1024)}
            ).status_code,
            413,
        )

    def test_profile_reassignment_keeps_completed_history_with_original_profile(self):
        profile_id = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id=profile_id,
                    workspace_id=self.workspace,
                    display_name="Fictional destination",
                )
            )
            db.session.commit()
        routine_id = self.create()
        values = self.edit_values(routine_id, profile_id=profile_id)
        self.assertEqual(
            post(self.client, f"/routines/{routine_id}/builder", values).status_code,
            302,
        )
        self.assertEqual(self.client.get(f"/routines/{routine_id}").status_code, 200)
        post(self.client, "/workspaces/profiles/select", {"profile_id": ""})
        self.assertEqual(self.client.get(f"/routines/{routine_id}").status_code, 404)
        with self.app.app_context():
            legacy_id = db.session.scalar(
                select(Routine.id).where(
                    Routine.workspace_id == self.workspace,
                    Routine.is_checklist.is_(True),
                )
            )
        post(self.client, f"/routines/{legacy_id}/toggle")
        values = self.edit_values(legacy_id, profile_id=profile_id)
        response = post(self.client, f"/routines/{legacy_id}/builder", values)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Duplicate it for another profile", response.text)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Routine, legacy_id).profile_id)
            snapshot = db.session.scalar(
                select(RoutineCompletionSnapshot).where(
                    RoutineCompletionSnapshot.routine_id == legacy_id
                )
            )
            self.assertEqual(snapshot.workspace_id, self.workspace)
            self.assertIsNone(snapshot.profile_id)
