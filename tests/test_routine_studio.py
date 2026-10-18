"""Optional timers preserve step identity and freeze into existing guided runs."""

import unittest, uuid
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import RoutineStep, RoutineSessionStep
import test_routine_builder as fixtures
from support import post


class RoutineStudioTests(unittest.TestCase):
    setUp = fixtures.RoutineBuilderTests.setUp
    tearDown = fixtures.RoutineBuilderTests.tearDown
    values = fixtures.RoutineBuilderTests.values

    def test_timer_persistence_order_snapshot_print_and_conflict(self):
        response = post(
            self.client,
            "/routines/new",
            self.values(step_timer_seconds=["60", "0", "120"]),
        )
        self.assertEqual(response.status_code, 302, response.text)
        url = response.location
        rid = int(url.rsplit("/", 1)[1])
        with self.app.app_context():
            steps = list(
                db.session.scalars(
                    select(RoutineStep)
                    .where(RoutineStep.routine_id == rid)
                    .order_by(RoutineStep.position)
                )
            )
            ids = [s.id for s in steps]
            self.assertEqual([s.timer_seconds for s in steps], [60, 0, 120])
        started = post(self.client, url + "/start", dict(launch_key=uuid.uuid4().hex))
        self.assertEqual(started.status_code, 302, started.text)
        with self.app.app_context():
            frozen = list(
                db.session.scalars(
                    select(RoutineSessionStep).order_by(RoutineSessionStep.position)
                )
            )
            self.assertEqual([s.timer_seconds for s in frozen], [60, 0, 120])
        reordered = self.values(
            version="1",
            step_id=ids[::-1],
            step_title=["Read a story", "Share breakfast", "Choose clothes"],
            step_icon=["book", "sun", "person"],
            step_description=["", "", ""],
            step_timer_seconds=["10", "0", "30"],
        )
        self.assertEqual(
            post(self.client, url + "/builder", reordered).status_code, 302
        )
        self.assertEqual(
            post(self.client, url + "/builder", reordered).status_code, 409
        )
        with self.app.app_context():
            steps = list(
                db.session.scalars(
                    select(RoutineStep)
                    .where(RoutineStep.routine_id == rid)
                    .order_by(RoutineStep.position)
                )
            )
            self.assertEqual([s.id for s in steps], ids[::-1])
            self.assertEqual([s.timer_seconds for s in steps], [10, 0, 30])
            self.assertEqual(
                [
                    s.timer_seconds
                    for s in db.session.scalars(
                        select(RoutineSessionStep).order_by(RoutineSessionStep.position)
                    )
                ],
                [60, 0, 120],
            )
        printed = self.client.get(url + "/print")
        self.assertEqual(printed.status_code, 200)
        self.assertIn("Optional time guide: 10 seconds", printed.text)
        other = self.app.test_client()
        from support import login

        login(other, "fictional-other-builder@example.com")
        self.assertEqual(other.get(url + "/print").status_code, 404)

    def test_invalid_timers_duplicate_step_fallback_and_templates(self):
        for timers in [["-1", "0", "0"], ["3601", "0", "0"], ["2.5", "0", "0"], ["60"]]:
            self.assertEqual(
                post(
                    self.client, "/routines/new", self.values(step_timer_seconds=timers)
                ).status_code,
                422,
            )
        response = post(
            self.client,
            "/routines/new",
            self.values(
                builder_action="duplicate:0", step_timer_seconds=["60", "0", "0"]
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.text.count('name="step_id"'), 5
        )  # four draft rows plus inert template
        for name in ["after-school", "organization", "household", "communication"]:
            page = self.client.get("/routines/new?template=" + name)
            self.assertEqual(page.status_code, 200)
        # Legacy forms with no timer arrays remain accepted, defaulting every step to off.
        self.assertEqual(
            post(self.client, "/routines/new", self.values()).status_code, 302
        )
