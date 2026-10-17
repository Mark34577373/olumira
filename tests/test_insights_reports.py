"""Real metrics, secure previews/downloads, bounded exports and document content."""

import csv, io, re, uuid, unittest
from datetime import datetime, timezone
from unittest.mock import patch
from flask import session
from flask_login import login_user
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import Observation, Routine, RoutineSession, User, CareProfile
from services import routine_builder, routine_sessions, insights, reports
from services.workspaces import resolve_context
import test_communication as fixtures
from support import post, login


class InsightsReportTests(unittest.TestCase):
    setUp = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    shared = fixtures.CommunicationTests.shared

    def config(self, **changes):
        values = dict(
            title="Fictional Fern summary café Ω Ж 中文",
            profile_id="",
            scope_workspace=self.ws,
            period="custom",
            **{"from": "2026-10-16", "to": "2026-10-17"},
            timezone="America/Chicago",
            grouping="daily",
            category="",
            format="pdf",
            sections=list(reports.SECTIONS),
            action="preview",
        )
        values.update(changes)
        return values

    def create_observation(self, **changes):
        values = dict(
            activity="Fictional observation café Ω Ж 中文",
            date="2026-10-17",
            time="00:00",
            timezone="America/Chicago",
            notes="Private fictional note",
            category="Achievements",
            tags="independent",
            profile_id="",
            scope_workspace=self.ws,
        )
        values.update(changes)
        response = post(self.client, "/observations", values)
        self.assertEqual(response.status_code, 302, response.status_code)

    def seed_run(self):
        with self.app.app_context(), self.app.test_request_context("/"):
            login_user(db.session.get(User, self.uid))
            session["workspace_id"] = self.ws
            resolve_context()
            rid, _ = routine_builder.save(
                dict(
                    name="Fictional guided morning",
                    description="",
                    category="Morning",
                    icon="sun",
                    color="sage",
                    profile_id="",
                    steps=[
                        dict(id="", title="Choose a book", description="", icon="book")
                    ],
                )
            )
            run = routine_sessions.start(rid, uuid.uuid4().hex)
            step = routine_sessions.steps_for(run)[0]
            moment = datetime(2026, 10, 17, 5, 0, tzinfo=timezone.utc)
            with patch("services.routine_sessions.utcnow", return_value=moment):
                routine_sessions.mutate(run, "complete", 1, uuid.uuid4().hex, step.id)
            return rid, run

    def data(self, **changes):
        with self.app.app_context(), self.app.test_request_context("/"):
            login_user(db.session.get(User, self.uid))
            session["workspace_id"] = self.ws
            resolve_context()
            values = self.config(**changes)
            return insights.calculate(insights.period(values), values["category"])

    def preview(self, values):
        response = post(self.client, "/observations/reports", values)
        self.assertEqual(response.status_code, 200, response.status_code)
        match = re.search(
            r'name="preview_digest" value="([a-f0-9]{64})"', response.text
        )
        self.assertIsNotNone(match)
        return response, dict(values, action="download", preview_digest=match.group(1))

    def test_real_metrics_zero_days_archive_and_date_boundaries(self):
        rid, _ = self.seed_run()
        self.create_observation()
        self.create_observation(time="", activity="Date only")
        self.create_observation(time="23:59", date="2026-10-15")
        data = self.data()
        self.assertEqual(data["stats"]["routine_completions"], 1)
        self.assertEqual(data["stats"]["observations"], 1)
        self.assertEqual(data["stats"]["date_only_observations"], 1)
        self.assertEqual([p["routines"] for p in data["chart"]], [0, 1])
        self.assertIsNone(data["completion_rate"]["denominator"])
        with self.app.app_context():
            db.session.get(Routine, rid).archived_at = datetime.now(timezone.utc)
            row = db.session.scalar(
                select(Observation).where(
                    Observation.activity.like("Fictional observation%"),
                    Observation.date == "2026-10-17",
                )
            )
            row.archived_at = datetime.now(timezone.utc)
            db.session.commit()
        data = self.data(grouping="weekly")
        self.assertEqual(data["stats"]["routine_completions"], 1)
        self.assertEqual(data["stats"]["observations"], 0)
        self.assertEqual(len(data["chart"]), 1)
        html = self.client.get(
            "/observations/insights?period=custom&from=2026-10-16&to=2026-10-17"
        ).text
        self.assertIn("Exact trend counts", html)
        self.assertIn("Scheduled completion rate: unavailable", html)
        self.assertEqual(
            self.client.get(
                "/observations/insights?period=custom&from=2024-01-01&to=2026-01-01"
            ).status_code,
            422,
        )
        with self.app.app_context():
            p = insights.period(
                self.config(**{"from": "2026-03-08", "to": "2026-03-08"})
            )
            self.assertEqual((p.upper - p.lower).total_seconds(), 23 * 3600)
            p = insights.period(
                self.config(**{"from": "2026-11-01", "to": "2026-11-01"})
            )
            self.assertEqual((p.upper - p.lower).total_seconds(), 25 * 3600)

    def test_task_and_handoff_metrics_use_real_completion_and_acknowledgment(self):
        helper = self.shared("caregiver")
        task = post(
            self.client,
            "/care/tasks/new",
            dict(
                title="Fictional completed report task",
                description="Fictional only",
                profile_id="",
                assigned_to=self.other,
                routine_id="",
                due_at="",
                timezone="America/Chicago",
                priority="normal",
                creation_key=uuid.uuid4().hex,
                scope_workspace=self.ws,
            ),
        )
        self.assertEqual(task.status_code, 302)
        identity = task.location.rsplit("/", 1)[1]
        with patch(
            "services.care_coordination.utcnow",
            return_value=datetime(2026, 10, 17, 6, tzinfo=timezone.utc),
        ):
            for _ in range(2):
                self.assertEqual(
                    post(
                        helper,
                        f"/care/tasks/{identity}/status/completed",
                        dict(scope_workspace=self.ws, version=1),
                    ).status_code,
                    302,
                )
        handoff = post(
            self.client,
            "/care/handoffs/new",
            dict(
                summary="Fictional report handoff",
                profile_id="",
                recipient=self.other,
                routine_id="",
                observation_id="",
                creation_key=uuid.uuid4().hex,
                scope_workspace=self.ws,
            ),
        )
        self.assertEqual(handoff.status_code, 302)
        hid = handoff.location.rsplit("/", 1)[1]
        self.assertEqual(self.data()["stats"]["completed_tasks"], 1)
        self.assertEqual(self.data()["stats"]["pending_handoffs"], 1)
        self.assertEqual(
            self.data(**{"from": "2020-01-01", "to": "2020-01-01"})["stats"][
                "pending_handoffs"
            ],
            1,
        )
        post(helper, f"/care/handoffs/{hid}/acknowledge", dict(scope_workspace=self.ws))
        self.assertEqual(self.data()["stats"]["pending_handoffs"], 0)
        _, download = self.preview(self.config(format="csv", sections=["tasks"]))
        response = post(self.client, "/observations/reports", download)
        self.assertIn("Fictional completed report task", response.data.decode())
        self.assertNotIn("Fictional report handoff", response.data.decode())

    def test_pdf_csv_preview_content_headers_formula_and_stale_data(self):
        self.seed_run()
        self.create_observation(
            notes='=HYPERLINK("https://fictional.invalid")',
            activity="Fictional café Ω Ж 中文",
        )
        values = self.config()
        preview, download = self.preview(values)
        pdf = post(self.client, "/observations/reports", download)
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.data.startswith(b"%PDF-"))
        self.assertIn("no-store", pdf.headers["Cache-Control"])
        self.assertIn(
            "attachment; filename=olumira-caregiver-report.pdf",
            pdf.headers["Content-Disposition"],
        )
        from pypdf import PdfReader

        text = "\n".join(
            page.extract_text() for page in PdfReader(io.BytesIO(pdf.data)).pages
        )
        self.assertIn("Fictional café", text)
        self.assertIn("Ω", text)
        self.assertIn("中文", text)
        self.assertIn("Ж", text)
        self.assertIn("Private", preview.headers["Cache-Control"].capitalize())
        values = self.config(format="csv", sections=["details"])
        preview, download = self.preview(values)
        response = post(self.client, "/observations/reports", download)
        rows = list(csv.DictReader(io.StringIO(response.data.decode("utf-8-sig"))))
        note = next(r for r in rows if r["field"] == "description")
        self.assertTrue(note["value"].startswith("'=HYPERLINK"))
        self.assertFalse(any(r["dataset"] == "overview" for r in rows))
        self.assertIn("text/csv", response.content_type)
        self.create_observation(activity="Newer fictional entry")
        self.assertEqual(
            post(self.client, "/observations/reports", download).status_code, 409
        )
        for value in ["=1", " +1", "\t@x", "\n-2", "\r=3", "\ufeff=4"]:
            self.assertTrue(reports.safe_cell(value).startswith("'"), value)

    def test_roles_profiles_limits_and_invalid_configuration(self):
        self.create_observation()
        viewer = self.shared("viewer")
        self.assertEqual(viewer.get("/observations/insights").status_code, 200)
        self.assertEqual(viewer.get("/observations/reports").status_code, 403)
        self.assertEqual(
            post(viewer, "/observations/reports", self.config()).status_code, 403
        )
        outsider = self.app.test_client()
        login(outsider, "fiction-other-board@example.com")
        response = outsider.get("/observations/insights")
        self.assertNotIn("Private fictional note", response.text)
        self.assertEqual(
            post(
                self.client, "/observations/reports", self.config(profile_id="x" * 32)
            ).status_code,
            404,
        )
        self.assertEqual(
            post(
                self.client, "/observations/reports", self.config(sections=[])
            ).status_code,
            422,
        )
        self.assertEqual(
            post(
                self.client, "/observations/reports", self.config(format="html")
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post("/observations/reports", data=self.config()).status_code,
            400,
        )
        with patch("services.reports.MAX_ROWS", 0):
            self.assertEqual(
                post(self.client, "/observations/reports", self.config()).status_code,
                422,
            )
        with patch("services.reports.MAX_TEXT_UNITS", 10):
            self.assertEqual(
                post(self.client, "/observations/reports", self.config()).status_code,
                422,
            )
        with self.app.app_context():
            db.session.add(
                CareProfile(
                    id="p" * 32,
                    workspace_id=self.ws,
                    display_name="Fictional empty profile",
                )
            )
            db.session.commit()
        response, _ = self.preview(self.config(profile_id="p" * 32))
        self.assertNotIn("Private fictional note", response.text)
        self.assertEqual(self.data(category="Different")["stats"]["observations"], 0)

    def test_multipage_long_text_and_pdf_visual_fixture(self):
        for i in range(6):
            self.create_observation(
                activity=f"Fictional long note {i}",
                notes=("A fictional café moment Ω Ж 中文. " * 65)[:2000],
            )
        _, download = self.preview(self.config())
        response = post(self.client, "/observations/reports", download)
        self.assertEqual(response.status_code, 200, response.status_code)
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(response.data))
        self.assertGreaterEqual(len(reader.pages), 4)
        for n, page in enumerate(reader.pages, 1):
            self.assertIn(f"Page {n}", page.extract_text())
        from pathlib import Path

        artifact = Path("artifacts/day29-32")
        artifact.mkdir(parents=True, exist_ok=True)
        (artifact / "fictional-caregiver-report.pdf").write_bytes(response.data)
