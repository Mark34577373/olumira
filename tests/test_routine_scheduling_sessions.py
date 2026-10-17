"""Days 23–24: actual CSRF forms, timezone rules, shared runs and frozen history."""

import concurrent.futures
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest
import uuid
from pathlib import Path
from flask_migrate import upgrade
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    Routine,
    RoutineSchedule,
    RoutineScheduleRevision,
    RoutineOccurrence,
    RoutineSession,
    RoutineSessionStep,
    RoutineSessionEvent,
    RoutineLaunchRequest,
    WorkspaceMembership,
    CareProfile,
)
from services import routine_scheduling as scheduling
from support import create_user, login, post, csrf_token

NOW = datetime(2030, 3, 1, 0, tzinfo=timezone.utc)


class SchedulingSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "APP_ENV": "testing",
                "DATABASE": str(Path(self.temp.name) / "runs.db"),
                "AUTH_LOGIN_IP_LIMIT": "1000 per hour",
                "AUTH_LOGIN_ACCOUNT_LIMIT": "1000 per hour",
            }
        )
        with self.app.app_context():
            upgrade()
        self.user, self.workspace = create_user(self.app, "fiction-runs@example.com")
        self.helper, self.helper_workspace = create_user(
            self.app, "fiction-helper-runs@example.com"
        )
        self.client = self.app.test_client()
        login(self.client, "fiction-runs@example.com")
        self.clock = patch("services.routine_scheduling.utcnow", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        response = post(
            self.client,
            "/routines/new",
            dict(
                name="Fictional woodland morning",
                description="A fictional demonstration.",
                category="Morning",
                icon="leaf",
                color="sage",
                profile_id="",
                version="",
                step_id=["", "", ""],
                step_title=["Choose clothes", "Share breakfast", "Read a story"],
                step_description=["Take your time.", "", "A familiar book."],
                step_icon=["person", "sun", "book"],
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.rid = int(response.location.rsplit("/", 1)[1])

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp.cleanup()

    def schedule_values(self, **changes):
        values = dict(
            timezone="America/Chicago",
            local_time="07:00",
            frequency="weekdays",
            weekdays=["0", "1", "2", "3", "4"],
            start_date="2030-03-04",
            end_date="",
            version="",
        )
        values.update(changes)
        return values

    def schedule(self, **changes):
        response = post(
            self.client,
            f"/routines/{self.rid}/schedule",
            self.schedule_values(**changes),
        )
        self.assertEqual(response.status_code, 302, response.text)
        with self.app.app_context():
            schedule = db.session.scalar(
                select(RoutineSchedule)
                .where(RoutineSchedule.routine_id == self.rid)
                .order_by(RoutineSchedule.created_at.desc())
            )
            revision = scheduling.current_revision(schedule)
            return schedule.id, revision.id

    def start(self, client=None, key=None, revision=None, day="2030-03-04"):
        return post(
            client or self.client,
            f"/routines/{self.rid}/start",
            dict(
                launch_key=key or uuid.uuid4().hex,
                revision_id=revision or "",
                local_date=day,
            ),
        )

    def run_state(self, sid):
        with self.app.app_context():
            run = db.session.get(RoutineSession, sid)
            steps = list(
                db.session.scalars(
                    select(RoutineSessionStep)
                    .where(RoutineSessionStep.session_id == sid)
                    .order_by(RoutineSessionStep.position)
                )
            )
            return dict(
                version=run.version,
                status=run.status,
                title=run.title,
                steps=[
                    dict(
                        id=s.id,
                        title=s.title,
                        done=bool(s.completed_at),
                        actor=s.completed_by,
                    )
                    for s in steps
                ],
            )

    def action(self, sid, action, step=None, version=None, key=None, client=None):
        values = dict(
            action=action,
            version=version if version is not None else self.run_state(sid)["version"],
            action_id=key or uuid.uuid4().hex,
            mode="guided",
        )
        if step:
            values["step_id"] = step
        return post(client or self.client, f"/routines/sessions/{sid}/action", values)

    def share(self, role="caregiver"):
        with self.app.app_context():
            db.session.add(
                WorkspaceMembership(
                    id=uuid.uuid4().hex,
                    workspace_id=self.workspace,
                    user_id=self.helper,
                    role=role,
                    status="active",
                )
            )
            db.session.commit()
        client = self.app.test_client()
        login(client, "fiction-helper-runs@example.com")
        with client.session_transaction() as context:
            context["workspace_id"] = self.workspace
        return client

    def test_daily_weekly_selected_and_one_time_calendar(self):
        for frequency, days, count in [
            ("daily", [], 7),
            ("weekly", [], 1),
            ("weekdays", ["0", "2", "4"], 3),
            ("once", [], 1),
        ]:
            with self.subTest(frequency=frequency):
                sid, rev = self.schedule(
                    frequency=frequency,
                    weekdays=days,
                    local_time={
                        "daily": "07:00",
                        "weekly": "08:00",
                        "weekdays": "09:00",
                        "once": "10:00",
                    }[frequency],
                )
                response = self.client.get(
                    "/routines/calendar?date=2030-03-04&view=week&timezone=UTC"
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.text.count(f'value="{rev}"'), count)
        day = self.client.get(
            "/routines/calendar?date=2030-03-05&view=day&timezone=UTC"
        )
        self.assertEqual(day.status_code, 200)
        self.assertNotIn('value="bad-revision"', day.text)

    def test_timezone_day_boundaries_and_upcoming_dashboard(self):
        _, rev = self.schedule(
            frequency="once",
            start_date="2030-03-01",
            local_time="19:00",
            timezone="America/Los_Angeles",
        )
        response = self.client.get(
            "/routines/calendar?date=2030-03-02&view=day&timezone=UTC"
        )
        self.assertIn("03:00", response.text)
        self.assertIn(rev, response.text)
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("Fictional woodland morning", home.text)
        self.assertIn("Upcoming schedule", home.text)
        self.assertIn('href="/calendar"', home.text)
        self.assertIn(
            "Guided runs and daily checklist marks are counted separately", home.text
        )

    def test_validation_duplicate_schedule_stale_edit_and_bad_dates(self):
        schedule, _ = self.schedule()
        self.assertEqual(
            post(
                self.client, f"/routines/{self.rid}/schedule", self.schedule_values()
            ).status_code,
            422,
        )
        bad = [
            dict(timezone="Mars/Invalid"),
            dict(local_time="25:00"),
            dict(frequency="unknown"),
            dict(weekdays=[]),
            dict(weekdays=["7"]),
            dict(start_date="2030-02-30"),
            dict(end_date="2030-01-01"),
            dict(frequency="once", start_date="2020-01-01"),
            dict(frequency="once", start_date="2030-03-10", local_time="02:30"),
        ]
        for changes in bad:
            with self.subTest(changes=changes):
                self.assertEqual(
                    post(
                        self.client,
                        f"/routines/{self.rid}/schedule",
                        self.schedule_values(**changes),
                    ).status_code,
                    422,
                )
        self.assertEqual(
            post(
                self.client,
                f"/routines/{self.rid}/schedule/{schedule}",
                self.schedule_values(version="0"),
            ).status_code,
            409,
        )
        for path in [
            "/routines/calendar?date=bad",
            "/routines/calendar?view=year",
            "/routines/calendar?timezone=Mars/Invalid",
            "/routines/calendar?date=9998-01-01",
            "/routines/history?page=0",
            "/routines/history?status=unknown",
            "/routines/history?from=2030-03-05&to=2030-03-01",
        ]:
            self.assertEqual(self.client.get(path).status_code, 400, path)

    def test_dst_gap_skipped_and_fold_first_occurrence(self):
        with self.app.app_context():
            self.assertIsNone(
                scheduling.local_instant(date(2030, 3, 10), "02:30", "America/Chicago")
            )
            self.assertEqual(
                scheduling.local_instant(date(2030, 11, 3), "01:30", "America/Chicago"),
                datetime(2030, 11, 3, 6, 30, tzinfo=timezone.utc),
            )
            rule = SimpleNamespace(
                start_date="2030-03-01",
                end_date=None,
                frequency="daily",
                weekdays="",
                local_time="02:30",
                timezone="America/Chicago",
                valid_from=NOW,
                valid_until=None,
            )
            self.assertIsNone(scheduling.candidate(rule, date(2030, 3, 10)))
            self.assertEqual(scheduling.candidate(rule, date(2030, 3, 11)).hour, 7)

    def test_edit_pause_resume_end_preserve_past_and_started_occurrence(self):
        schedule, revision = self.schedule()
        started = self.start(revision=revision)
        self.assertEqual(started.status_code, 302, started.text)
        sid = started.location.rsplit("/", 1)[1]
        response = post(
            self.client,
            f"/routines/{self.rid}/schedule/{schedule}",
            self.schedule_values(version="1", local_time="08:30"),
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(
                    select(func.count()).select_from(RoutineScheduleRevision)
                ),
                2,
            )
            self.assertEqual(
                db.session.get(
                    RoutineOccurrence,
                    scheduling.occurrence_id(revision, date(2030, 3, 4)),
                ).local_time,
                "07:00",
            )
        response = self.client.get("/routines/calendar?date=2030-03-04&view=day")
        self.assertIn("07:00", response.text)
        self.assertIn("08:30", response.text)
        self.assertIn(sid, response.text)
        self.assertEqual(
            post(
                self.client, f"/routines/schedules/{schedule}/pause", dict(version="2")
            ).status_code,
            302,
        )
        paused = self.client.get("/routines/calendar?date=2030-03-05&view=day")
        self.assertNotIn('name="revision_id"', paused.text)
        self.assertEqual(
            post(
                self.client, f"/routines/schedules/{schedule}/resume", dict(version="3")
            ).status_code,
            302,
        )
        self.assertEqual(
            post(
                self.client, f"/routines/schedules/{schedule}/end", dict(version="4")
            ).status_code,
            302,
        )
        self.assertEqual(
            post(
                self.client, f"/routines/schedules/{schedule}/resume", dict(version="5")
            ).status_code,
            409,
        )
        self.assertEqual(self.client.get(started.location).status_code, 200)

    def test_overlaps_permitted_and_exact_duplicates_rejected(self):
        self.schedule(frequency="daily")
        self.schedule(frequency="weekly")
        response = self.client.get("/routines/calendar?date=2030-03-04&view=day")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.count("Shared start time"), 2)

    def test_occurrences_generated_without_get_writes_or_duplicates(self):
        _, revision = self.schedule()
        for _ in range(3):
            self.assertEqual(
                self.client.get("/routines/calendar?date=2030-03-04").status_code, 200
            )
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(RoutineOccurrence)),
                0,
            )
        first = self.start(revision=revision)
        self.assertEqual(self.start(revision=revision).location, first.location)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(RoutineOccurrence)),
                1,
            )
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(RoutineSession)), 1
            )

    def test_scheduled_launch_outside_window_and_invalid_reference(self):
        _, revision = self.schedule()
        self.assertEqual(
            self.start(revision=revision, day="2031-03-04").status_code, 409
        )
        self.assertEqual(self.start(revision="f" * 32).status_code, 404)
        self.assertEqual(
            self.start(revision=revision, day="not-a-date").status_code, 409
        )

    def test_full_guided_flow_undo_pause_resume_and_saved_history(self):
        response = self.start()
        self.assertEqual(response.status_code, 302, response.text)
        sid = response.location.rsplit("/", 1)[1]
        player = self.client.get(response.location)
        self.assertEqual(player.status_code, 200, player.text)
        self.assertIn("STEP 1 OF 3", player.text)
        state = self.run_state(sid)
        self.assertEqual(
            self.action(sid, "complete", state["steps"][0]["id"]).status_code, 302
        )
        self.assertEqual(
            self.action(sid, "undo", state["steps"][0]["id"]).status_code, 302
        )
        self.assertFalse(self.run_state(sid)["steps"][0]["done"])
        self.action(sid, "complete", state["steps"][0]["id"])
        self.action(sid, "pause")
        self.assertEqual(self.run_state(sid)["status"], "paused")
        self.assertEqual(
            self.action(sid, "complete", state["steps"][1]["id"]).status_code, 409
        )
        self.assertIn(
            "Take all the time you need", self.client.get(response.location).text
        )
        login(self.client, "fiction-runs@example.com")
        self.assertEqual(self.start().location, response.location)
        self.action(sid, "resume")
        for step in state["steps"][1:]:
            self.assertEqual(self.action(sid, "complete", step["id"]).status_code, 302)
        self.assertEqual(self.run_state(sid)["status"], "completed")
        self.assertIn("You did it, together.", self.client.get(response.location).text)
        self.assertEqual(
            self.action(sid, "undo", state["steps"][0]["id"]).status_code, 409
        )
        history = self.client.get("/routines/history?status=completed")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertIn("3 of 3 steps", history.text)
        self.assertIn("Fictional woodland morning", history.text)
        self.assertEqual(
            self.client.get("/routines/history?status=paused").text.count(
                "View completed run"
            ),
            0,
        )

    def test_idempotent_launch_retry_even_after_completion_and_explicit_new_run(self):
        key, alias = uuid.uuid4().hex, uuid.uuid4().hex
        response = self.start(key=key)
        self.assertEqual(self.start(key=key).location, response.location)
        self.assertEqual(self.start(key=alias).location, response.location)
        sid = response.location.rsplit("/", 1)[1]
        for step in self.run_state(sid)["steps"]:
            self.action(sid, "complete", step["id"])
        self.assertEqual(self.start(key=key).location, response.location)
        self.assertEqual(self.start(key=alias).location, response.location)
        self.assertNotEqual(self.start().location, response.location)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(RoutineSession)), 2
            )

    def test_idempotent_mutation_and_stale_caregiver_conflict(self):
        response = self.start()
        sid = response.location.rsplit("/", 1)[1]
        state = self.run_state(sid)
        key = uuid.uuid4().hex
        first = state["steps"][0]["id"]
        self.assertEqual(
            self.action(sid, "complete", first, version=1, key=key).status_code, 302
        )
        self.assertEqual(
            self.action(sid, "complete", first, version=1, key=key).status_code, 302
        )
        self.assertEqual(self.run_state(sid)["version"], 2)
        conflict = self.action(sid, "complete", state["steps"][1]["id"], version=1)
        self.assertEqual(conflict.status_code, 409)
        self.assertIn("Another caregiver updated", conflict.text)
        self.assertFalse(self.run_state(sid)["steps"][1]["done"])
        self.assertEqual(self.action(sid, "undo", first, key=key).status_code, 400)

    def test_template_edits_archive_and_restore_do_not_change_session_snapshots(self):
        schedule, _ = self.schedule()
        response = self.start()
        sid = response.location.rsplit("/", 1)[1]
        from services.routine_builder import draft

        with self.app.app_context():
            values = draft(db.session.get(Routine, self.rid))
        steps = values.pop("steps")
        for key in ["id", "title", "description", "icon"]:
            values["step_" + key] = [s[key] for s in steps]
        values["name"] = "Fictional changed title"
        values["step_title"][0] = "A new first step"
        self.assertEqual(
            post(self.client, f"/routines/{self.rid}/builder", values).status_code, 302
        )
        self.assertEqual(self.run_state(sid)["title"], "Fictional woodland morning")
        self.assertEqual(self.run_state(sid)["steps"][0]["title"], "Choose clothes")
        self.assertEqual(
            post(
                self.client, f"/routines/{self.rid}/archive", dict(version="2")
            ).status_code,
            302,
        )
        self.assertEqual(self.client.get(response.location).status_code, 200)
        self.assertEqual(
            self.action(
                sid, "complete", self.run_state(sid)["steps"][0]["id"]
            ).status_code,
            302,
        )
        self.assertEqual(
            post(
                self.client, f"/routines/{self.rid}/restore", dict(version="3")
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertEqual(db.session.get(RoutineSchedule, schedule).state, "paused")

    def test_caregiver_shared_progress_attribution_and_live_version(self):
        helper = self.share()
        response = self.start()
        sid = response.location.rsplit("/", 1)[1]
        state = self.run_state(sid)
        self.assertEqual(self.start(client=helper).location, response.location)
        self.assertEqual(
            self.action(
                sid, "complete", state["steps"][0]["id"], client=helper
            ).status_code,
            302,
        )
        self.assertEqual(self.run_state(sid)["steps"][0]["actor"], self.helper)
        version = self.client.get(f"/routines/sessions/{sid}/state")
        self.assertEqual(version.json["version"], 2)
        self.assertIn("Completed a step", self.client.get(response.location).text)

    def test_viewer_csrf_revocation_and_unrelated_family_isolation(self):
        viewer = self.share("viewer")
        schedule, revision = self.schedule()
        response = self.start()
        sid = response.location.rsplit("/", 1)[1]
        step = self.run_state(sid)["steps"][0]["id"]
        self.assertEqual(viewer.get(response.location).status_code, 200)
        for request in [
            lambda: self.start(client=viewer),
            lambda: self.action(sid, "complete", step, client=viewer),
            lambda: post(
                viewer, f"/routines/{self.rid}/schedule", self.schedule_values()
            ),
            lambda: post(
                viewer, f"/routines/schedules/{schedule}/pause", dict(version="1")
            ),
        ]:
            self.assertEqual(request().status_code, 403)
        for path, values in [
            (f"/routines/{self.rid}/start", dict(launch_key=uuid.uuid4().hex)),
            (f"/routines/{self.rid}/schedule", self.schedule_values()),
            (
                f"/routines/sessions/{sid}/action",
                dict(action="pause", version="1", action_id=uuid.uuid4().hex),
            ),
            (f"/routines/schedules/{schedule}/pause", dict(version="1")),
        ]:
            self.assertEqual(self.client.post(path, data=values).status_code, 400)
        with viewer.session_transaction() as context:
            context["workspace_id"] = self.helper_workspace
        for path in [
            response.location,
            f"/routines/sessions/{sid}/state",
            f"/routines/{self.rid}/schedule/{schedule}",
        ]:
            self.assertEqual(viewer.get(path).status_code, 404)
        self.assertEqual(self.start(client=viewer, revision=revision).status_code, 404)
        self.assertNotIn(
            "Fictional woodland morning", viewer.get("/routines/history").text
        )
        with self.app.app_context():
            member = db.session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == self.workspace,
                    WorkspaceMembership.user_id == self.helper,
                )
            )
            member.status = "revoked"
            db.session.commit()
        with viewer.session_transaction() as context:
            context["workspace_id"] = self.workspace
        self.assertEqual(viewer.get(response.location).status_code, 404)

    def test_profile_scope_frozen_and_reassignment_blocked(self):
        profile = uuid.uuid4().hex
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id=profile,
                    workspace_id=self.workspace,
                    display_name="Fictional Fern",
                )
            )
            db.session.commit()
        response = self.start()
        sid = response.location.rsplit("/", 1)[1]
        with self.client.session_transaction() as context:
            context["profile_id"] = profile
        self.assertEqual(self.client.get(response.location).status_code, 404)
        self.assertNotIn(
            "Fictional woodland morning", self.client.get("/routines/history").text
        )
        with self.client.session_transaction() as context:
            context.pop("profile_id", None)
        from services.routine_builder import draft

        with self.app.app_context():
            values = draft(db.session.get(Routine, self.rid))
        steps = values.pop("steps")
        for key in ["id", "title", "description", "icon"]:
            values["step_" + key] = [s[key] for s in steps]
        values["profile_id"] = profile
        self.assertEqual(
            post(self.client, f"/routines/{self.rid}/builder", values).status_code, 422
        )
        self.assertEqual(self.client.get(response.location).status_code, 200)

    def test_partial_launch_failure_rolls_back_every_record(self):
        _, revision = self.schedule()
        with patch(
            "services.routine_sessions.event",
            side_effect=RuntimeError("fictional failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.start(revision=revision)
        with self.app.app_context():
            for model in [
                RoutineOccurrence,
                RoutineSession,
                RoutineSessionStep,
                RoutineSessionEvent,
                RoutineLaunchRequest,
            ]:
                self.assertEqual(
                    db.session.scalar(select(func.count()).select_from(model)), 0
                )

    def test_concurrent_launch_and_step_completion_serialized(self):
        helper = self.share()
        # Pre-obtain CSRF, so competing launch requests hit the actual mutation boundary.
        tokens = [csrf_token(c) for c in [self.client, helper]]

        def launch(pair):
            client, token = pair
            return client.post(
                f"/routines/{self.rid}/start",
                data=dict(csrf_token=token, launch_key=uuid.uuid4().hex),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(launch, zip([self.client, helper], tokens)))
        self.assertEqual([r.status_code for r in responses], [302, 302])
        self.assertEqual(responses[0].location, responses[1].location)
        sid = responses[0].location.rsplit("/", 1)[1]
        state = self.run_state(sid)

        def complete(pair):
            client, token = pair
            return client.post(
                f"/routines/sessions/{sid}/action",
                data=dict(
                    csrf_token=token,
                    action="complete",
                    action_id=uuid.uuid4().hex,
                    version="1",
                    step_id=state["steps"][0]["id"],
                ),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(complete, zip([self.client, helper], tokens)))
        self.assertEqual(sorted(r.status_code for r in responses), [302, 409])
        self.assertEqual(self.run_state(sid)["version"], 2)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(RoutineSession)), 1
            )
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(RoutineSessionEvent)
                    .where(RoutineSessionEvent.action == "complete")
                ),
                1,
            )

    def test_history_pagination_limits_filters_and_frozen_completed_steps(self):
        response = self.start()
        sid = response.location.rsplit("/", 1)[1]
        state = self.run_state(sid)
        for step in state["steps"]:
            self.action(sid, "complete", step["id"])
        self.assertIn(
            "Fictional woodland morning",
            self.client.get(f"/routines/history?routine={self.rid}").text,
        )
        self.assertNotIn(
            "View completed run",
            self.client.get("/routines/history?from=2030-01-01").text,
        )
        self.assertEqual(
            self.client.get("/routines/history?routine=invalid").status_code, 400
        )
        self.assertEqual(self.client.get("/routines/history?page=2").status_code, 200)
        with self.app.app_context():
            self.assertIsNone(db.session.get(RoutineSession, sid).active_key)
            self.assertEqual(
                db.session.scalar(
                    select(func.count())
                    .select_from(RoutineSessionStep)
                    .where(
                        RoutineSessionStep.session_id == sid,
                        RoutineSessionStep.completed_at.is_not(None),
                    )
                ),
                3,
            )

    def test_database_scope_and_snapshot_guards(self):
        response = self.start()
        sid = response.location.rsplit("/", 1)[1]
        state = self.run_state(sid)
        with self.app.app_context():
            for statement, values in [
                (
                    "UPDATE routine_sessions SET title='Changed' WHERE id=:id",
                    dict(id=sid),
                ),
                (
                    "UPDATE routine_session_steps SET title='Changed' WHERE id=:id",
                    dict(id=state["steps"][0]["id"]),
                ),
                (
                    "UPDATE routine_sessions SET workspace_id=:workspace WHERE id=:id",
                    dict(id=sid, workspace=self.helper_workspace),
                ),
            ]:
                with self.assertRaises(IntegrityError):
                    db.session.execute(text(statement), values)
                    db.session.commit()
                db.session.rollback()
        for step in state["steps"]:
            self.action(sid, "complete", step["id"])
        with self.app.app_context():
            for statement, values in [
                (
                    "UPDATE routine_sessions SET status='active' WHERE id=:id",
                    dict(id=sid),
                ),
                (
                    "UPDATE routine_session_steps SET completed_at=NULL WHERE id=:id",
                    dict(id=state["steps"][0]["id"]),
                ),
            ]:
                with self.assertRaises(IntegrityError):
                    db.session.execute(text(statement), values)
                    db.session.commit()
                db.session.rollback()

    def test_concurrent_scheduled_launch_materializes_exactly_once(self):
        helper = self.share()
        _, revision = self.schedule()
        tokens = [csrf_token(c) for c in [self.client, helper]]

        def launch(pair):
            client, token = pair
            return client.post(
                f"/routines/{self.rid}/start",
                data=dict(
                    csrf_token=token,
                    launch_key=uuid.uuid4().hex,
                    revision_id=revision,
                    local_date="2030-03-04",
                ),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(launch, zip([self.client, helper], tokens)))
        self.assertEqual([r.status_code for r in responses], [302, 302])
        self.assertEqual(responses[0].location, responses[1].location)
        with self.app.app_context():
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(RoutineOccurrence)),
                1,
            )
            self.assertEqual(
                db.session.scalar(select(func.count()).select_from(RoutineSession)), 1
            )

    def test_prior_recurrence_windows_survive_future_only_edit(self):
        schedule, revision = self.schedule(frequency="daily", start_date="2030-03-01")
        later = datetime(2030, 3, 5, 0, tzinfo=timezone.utc)
        with patch("services.routine_scheduling.utcnow", return_value=later):
            response = post(
                self.client,
                f"/routines/{self.rid}/schedule/{schedule}",
                self.schedule_values(
                    frequency="daily",
                    start_date="2030-03-01",
                    local_time="08:30",
                    version="1",
                ),
            )
            self.assertEqual(response.status_code, 302)
            response = self.client.get("/routines/calendar?date=2030-03-02&view=day")
            self.assertIn("07:00", response.text)
            self.assertNotIn("08:30</time>", response.text)
            response = self.client.get("/routines/calendar?date=2030-03-06&view=day")
            self.assertIn("08:30", response.text)
            self.assertNotIn("07:00</time>", response.text)
