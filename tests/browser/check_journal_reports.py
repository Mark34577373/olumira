"""Repeatable fictional journal -> timeline -> insights -> private PDF/CSV demo."""

import json, logging, sys, threading, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from flask import session
from flask_login import login_user
from olumira.extensions import db
from olumira.models import CareProfile, User
from services import routine_builder, routine_sessions
from services.workspaces import resolve_context
from support import PASSWORD, create_user
from test_communication import CommunicationTests


def main():
    fixture = CommunicationTests()
    fixture.setUp()
    checks = []
    layouts = 0
    artifact = ROOT / "artifacts/day29-32"
    artifact.mkdir(parents=True, exist_ok=True)
    profile = uuid.uuid4().hex
    try:
        fixture.shared("caregiver")
        outsider, _ = create_user(fixture.app, "fictional-journal-outsider@example.com")
        with fixture.app.app_context():
            db.session.add(
                CareProfile(
                    id=profile, workspace_id=fixture.ws, display_name="Fictional Fern"
                )
            )
            db.session.commit()
            with fixture.app.test_request_context("/"):
                login_user(db.session.get(User, fixture.uid))
                session["workspace_id"] = fixture.ws
                session["profile_id"] = profile
                resolve_context()
                rid, _ = routine_builder.save(
                    dict(
                        name="Fictional morning routine",
                        description="",
                        category="Morning",
                        icon="sun",
                        color="sage",
                        profile_id=profile,
                        steps=[
                            dict(
                                id="",
                                title="Choose a picture",
                                description="",
                                icon="book",
                            )
                        ],
                    )
                )
                run = routine_sessions.start(rid, uuid.uuid4().hex)
                step = routine_sessions.steps_for(run)[0]
                routine_sessions.mutate(run, "complete", 1, uuid.uuid4().hex, step.id)
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, fixture.app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        fixture.app.config["PUBLIC_APP_URL"] = origin
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport=dict(width=1440, height=1000))
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append("JavaScript error"))

            def sign_in(page, email, chosen=True):
                page.goto(origin + "/auth/login")
                page.locator("#email").fill(email)
                page.locator("#password").fill(PASSWORD)
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.locator("#active-workspace")).to_be_visible()
                if chosen:
                    page.locator("#active-workspace").select_option(fixture.ws)
                    page.get_by_role(
                        "button", name="Switch workspace", exact=True
                    ).click()
                    page.locator("#active-profile").select_option(profile)
                    page.get_by_role(
                        "button", name="Switch profile", exact=True
                    ).click()

            sign_in(page, "fiction-board@example.com")
            page.goto(origin + "/observations")
            page.get_by_text("Add an observation", exact=True).first.click()
            page.locator("#observation-activity").fill(
                "Completed Morning Routine Independently"
            )
            page.locator("#observation-time").fill("08:30")
            page.locator("#observation-category").fill("Achievements")
            page.locator("#observation-notes").fill(
                "Fictional Fern chose a picture and finished the morning routine."
            )
            page.locator("#observation-tags").fill("morning, independent")
            page.locator("#observation-session").select_option(run)
            page.get_by_role("button", name="Save observation", exact=True).click()
            expect(
                page.get_by_role("status").filter(has_text="Observation saved")
            ).to_be_visible()
            checks.append(
                "Create a structured profile observation through real CSRF form"
            )
            page.get_by_role("link", name="Timeline", exact=True).click()
            page.locator("#filter-category").select_option("Achievements")
            page.locator("#filter-tag").fill("independent")
            page.get_by_role("button", name="Apply filters", exact=True).click()
            expect(
                page.get_by_role("status").filter(has_text="1 matching")
            ).to_be_visible()
            page.get_by_role("link", name="View details", exact=True).click()
            detail = page.url
            page.get_by_role("link", name="Edit observation", exact=True).click()
            page.locator("#observation-notes").fill(
                "Fictional edited observation; the original author is preserved."
            )
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(
                page.get_by_text(
                    "Fictional edited observation; the original author is preserved.",
                    exact=True,
                )
            ).to_be_visible()
            page.get_by_role("link", name="Back to timeline", exact=True).click()
            expect(page.locator("#filter-tag")).to_have_value("independent")
            checks.append(
                "Combined timeline filters, linked detail and edit retain navigation context"
            )
            page.get_by_role("link", name="Insights", exact=True).click()
            expect(
                page.get_by_text("Scheduled completion rate: unavailable.", exact=True)
            ).to_be_visible()
            page.get_by_text("View exact trend counts", exact=True).click()
            expect(page.get_by_role("table")).to_be_visible()
            page.screenshot(path=str(artifact / "insights-desktop.png"), full_page=True)
            checks.append(
                "Real guided completion and observation trend with accessible table"
            )
            page.get_by_role("link", name="Reports", exact=True).click()
            page.locator("#report-title").fill("Fictional Fern caregiver summary")
            page.get_by_role("button", name="Preview report", exact=True).click()
            expect(page.locator("#report-preview-title")).to_have_text(
                "Fictional Fern caregiver summary"
            )
            with page.expect_download() as info:
                page.get_by_role("button", name="Download PDF", exact=True).click()
            download = info.value
            download.save_as(artifact / "fictional-browser-report.pdf")
            assert (
                (artifact / "fictional-browser-report.pdf")
                .read_bytes()
                .startswith(b"%PDF-")
            )
            page.locator("#report-format").select_option("csv")
            page.get_by_role("button", name="Preview report", exact=True).click()
            with page.expect_download() as info:
                page.get_by_role("button", name="Download CSV", exact=True).click()
            info.value.save_as(artifact / "fictional-browser-report.csv")
            assert (
                "Fictional edited observation"
                in (artifact / "fictional-browser-report.csv").read_text()
            )
            checks.append(
                "Preview and successful PDF/CSV browser downloads with actual data"
            )
            pages = [
                "/observations",
                "/observations/timeline",
                "/observations/insights",
                "/observations/reports",
                detail.replace(origin, ""),
                "/observations/"
                + detail.split("/observations/")[1].split("?")[0]
                + "/edit",
            ]
            for width in [320, 390, 768, 1024, 1440]:
                page.set_viewport_size(dict(width=width, height=900))
                for path in pages:
                    response = page.goto(origin + path)
                    assert response.status == 200, (width, path, response.status)
                    assert page.evaluate(
                        "document.documentElement.scrollWidth<=window.innerWidth+1"
                    ), (width, path, "overflow")
                    layouts += 1
                if width == 390:
                    page.goto(origin + "/observations/insights")
                    page.screenshot(
                        path=str(artifact / "insights-mobile.png"), full_page=True
                    )
            page.goto(origin + "/observations/reports")
            page.locator("#report-title").focus()
            page.keyboard.press("Tab")
            expect(page.locator("#report-profile")).to_be_focused()
            page.locator('button[value="preview"]').focus()
            page.keyboard.press("Enter")
            expect(page.locator("#report-preview-title")).to_be_visible()
            checks.append("30 viewport/page checks and keyboard form preview")
            helper = browser.new_page()
            sign_in(helper, "fiction-other-board@example.com")
            helper.goto(detail)
            expect(
                helper.get_by_role(
                    "heading", name="Completed Morning Routine Independently"
                )
            ).to_be_visible()
            helper.goto(origin + "/observations/reports")
            assert helper.locator("#report-title").is_visible()
            foreign = browser.new_page()
            sign_in(foreign, "fictional-journal-outsider@example.com", False)
            assert foreign.goto(detail).status == 404
            foreign.goto(origin + "/observations/insights")
            assert "Fictional edited observation" not in foreign.content()
            checks.append("Authorized caregiver access and unrelated workspace denial")
            assert not errors, errors
            browser.close()
        server.shutdown()
        print(
            json.dumps(
                dict(checks=checks, viewport_pages=layouts, failures=[]), indent=2
            )
        )
    finally:
        fixture.tearDown()


if __name__ == "__main__":
    main()
