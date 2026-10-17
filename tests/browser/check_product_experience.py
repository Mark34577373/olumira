"""Fictional registration → premium setup → calendar → resources → dashboard."""

import json, logging, sys, tempfile, threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from flask_migrate import upgrade
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from sqlalchemy import select, func
from olumira import create_app
from olumira.extensions import db
from olumira.models import User, OnboardingState, WorkspaceInvitation, ResourceBookmark
from test_account_recovery import email_link
from support import PASSWORD, create_user


def main():
    artifact = ROOT / "artifacts/day33-36"
    artifact.mkdir(parents=True, exist_ok=True)
    checks = []
    layouts = 0
    with tempfile.TemporaryDirectory() as folder:
        app = create_app(
            dict(
                APP_ENV="testing",
                DATABASE=str(Path(folder) / "demo.db"),
                AUTH_LOGIN_IP_LIMIT="1000 per hour",
                AUTH_LOGIN_ACCOUNT_LIMIT="1000 per hour",
            )
        )
        with app.app_context():
            upgrade()
        create_user(app, "fictional-unrelated@example.com")
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        app.config["PUBLIC_APP_URL"] = origin
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport=dict(width=1440, height=1000))
                page = context.new_page()
                errors = []
                page.on(
                    "pageerror", lambda error: errors.append("JavaScript runtime error")
                )
                page.goto(origin + "/auth/register")
                page.locator("#display_name").fill("Fictional Rowan")
                page.locator("#email").fill("fictional-first-use@example.com")
                page.locator("#password").fill(PASSWORD)
                page.locator("#confirm_password").fill(PASSWORD)
                page.locator(".auth-submit").click()
                expect(page).to_have_url(origin + "/auth/check-email")
                _, verification, _ = email_link(app, "verify_email")
                page.goto(verification)
                page.locator(".auth-submit").click()
                expect(
                    page.get_by_role("heading", name="Email verified", exact=True)
                ).to_be_visible()
                page.goto(origin + "/auth/login")
                page.locator("#email").fill("fictional-first-use@example.com")
                page.locator("#password").fill(PASSWORD)
                page.locator(".auth-submit").click()
                page.get_by_role("link", name="Start guided setup", exact=True).click()
                page.get_by_role("button", name="Get started", exact=True).click()
                expect(page.locator("#setup-heading")).to_have_text("Family workspace")
                checks.append(
                    "Registration, encrypted development verification, sign-in and premium welcome"
                )
                page.locator("select[name=workspace_action]").select_option("new")
                page.locator("input[name=workspace_name]").fill(
                    "Fictional Cedar Family"
                )
                page.get_by_role("button", name="Save and continue", exact=True).click()
                expect(page.locator("#setup-heading")).to_have_text("Care profile")
                page.locator("select[name=profile_action]").select_option("new")
                page.locator("input[name=profile_name]").fill("Fictional Fern")
                page.get_by_role("button", name="Save and continue", exact=True).click()
                expect(page.locator("#setup-heading")).to_have_text("Daily routines")
                page.get_by_role("link", name="Save and leave", exact=True).click()
                page.get_by_role("link", name="Resume guided setup", exact=True).click()
                expect(page.locator("#setup-heading")).to_have_text("Daily routines")
                page.locator("select[name=routine_template]").select_option("morning")
                page.get_by_role("button", name="Save and continue", exact=True).click()
                expect(page.locator("#setup-heading")).to_have_text(
                    "Communication setup"
                )
                page.locator("select[name=board_template]").select_option("needs")
                page.get_by_role("button", name="Save and continue", exact=True).click()
                expect(page.locator("#setup-heading")).to_have_text("Care team")
                checks.append(
                    "New workspace/profile, save/resume, real starter routine and picture board"
                )
                page.get_by_role(
                    "link", name="Open caregiver invitations", exact=True
                ).click()
                page.locator("#invite-email").fill("fictional-invited@example.com")
                page.get_by_role("button", name="Send invitation", exact=True).click()
                with app.app_context():
                    assert (
                        db.session.scalar(
                            select(func.count()).select_from(WorkspaceInvitation)
                        )
                        == 1
                    )
                page.goto(origin + "/setup")
                expect(page.locator("#setup-heading")).to_have_text("Care team")
                page.get_by_role(
                    "button", name="Skip this optional step", exact=True
                ).click()
                page.get_by_role(
                    "link", name="Open interactive product tour", exact=True
                ).click()
                page.get_by_role("link", name="Explore Dashboard", exact=True).click()
                expect(page.locator("#tour-coach-title")).to_have_text("Dashboard")
                page.get_by_role("link", name="Next feature", exact=True).click()
                expect(page.locator("#tour-coach-title")).to_have_text("Routines")
                page.get_by_role("link", name="Skip tour", exact=True).click()
                expect(page.locator("#tour-coach-title")).to_have_count(0)
                page.goto(origin + "/setup")
                page.get_by_role("button", name="Finish setup", exact=True).click()
                expect(
                    page.get_by_role("link", name="Enter Olumira", exact=True)
                ).to_be_visible()
                page.get_by_role("link", name="Enter Olumira", exact=True).click()
                expect(page.locator("#active-profile option:checked")).to_have_text(
                    "Fictional Fern"
                )
                checks.append(
                    "Optional real invitation, contextual product tour, completion and profile-aware dashboard"
                )
                with app.app_context():
                    uid = db.session.scalar(
                        select(User.id).where(
                            User.email == "fictional-first-use@example.com"
                        )
                    )
                    state = db.session.scalar(
                        select(OnboardingState).where(
                            OnboardingState.user_id == uid,
                            OnboardingState.completed_at.is_not(None),
                        )
                    )
                    rid = state.routine_id
                    profile = state.profile_id
                    ws = state.workspace_id
                day = (
                    (datetime.now(ZoneInfo("America/Chicago")) + timedelta(days=1))
                    .date()
                    .isoformat()
                )
                page.goto(origin + f"/routines/{rid}/schedule")
                page.locator("#schedule-date").fill(day)
                page.locator("#schedule-time").fill("09:00")
                page.locator("#schedule-repeat").select_option("daily")
                page.get_by_role("button", name="Save schedule", exact=True).click()
                page.goto(origin + "/care/tasks/new")
                page.locator("#care-task-title").fill("Fictional prepare picture cards")
                page.locator("#care-task-assignee").select_option(uid)
                page.locator("#care-task-due").fill(day + "T09:15")
                page.get_by_role("button", name="Save task", exact=True).click()
                page.goto(origin + "/calendar/new")
                page.locator("#event-title").fill("Fictional garden visit")
                page.locator("#event-start_date").fill(day)
                page.locator("#event-local_time").fill("10:00")
                page.locator("#event-end_date").fill(day)
                page.locator("#event-end_time").fill("11:00")
                page.get_by_role("button", name="Save event", exact=True).click()
                event_url = page.url
                expect(
                    page.get_by_role(
                        "heading", name="Fictional garden visit", exact=True
                    )
                ).to_be_visible()
                page.goto(origin + "/calendar?view=day&date=" + day)
                expect(
                    page.get_by_role("link", name="Morning preparation", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role(
                        "link", name="Fictional prepare picture cards", exact=True
                    )
                ).to_be_visible()
                expect(
                    page.get_by_role("link", name="Fictional garden visit", exact=True).first
                ).to_be_visible()
                checks.append(
                    "Calendar combines actual recurring routine, assigned task and custom event"
                )
                page.get_by_role(
                    "link", name="Reminder preferences", exact=True
                ).click()
                page.locator("select[name=lead_minutes]").select_option("1440")
                page.get_by_role(
                    "button", name="Save reminder preferences", exact=True
                ).click()
                expect(page.locator("select[name=lead_minutes]")).to_have_value("1440")
                page.goto(origin + "/resources")
                page.locator("#resource-search").fill("handoff")
                page.get_by_role("button", name="Search library", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Shared handoff notes", exact=True)
                ).to_be_visible()
                page.get_by_role("link", name="Open full guide", exact=True).click()
                page.get_by_role("button", name="Bookmark resource", exact=True).click()
                expect(
                    page.get_by_role("button", name="Remove bookmark", exact=True)
                ).to_be_visible()
                page.goto(origin + "/resources?saved=1")
                expect(
                    page.get_by_role("heading", name="Shared handoff notes", exact=True)
                ).to_be_visible()
                checks.append(
                    "Persistent reminder preferences, server search, full resource detail and bookmark"
                )
                page.goto(origin)
                expect(
                    page.get_by_role("heading", name="Upcoming schedule", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_role("link", name="Fictional garden visit", exact=True).first
                ).to_be_visible()
                page.screenshot(
                    path=str(artifact / "dashboard-desktop.png"), full_page=True
                )
                for width in [320, 390, 768, 1024, 1440]:
                    page.set_viewport_size(dict(width=width, height=900))
                    for path in [
                        "/",
                        "/setup",
                        "/tour",
                        "/calendar?view=month&date=" + day,
                        "/calendar?view=week&date=" + day,
                        "/calendar?view=day&date=" + day,
                        "/calendar?view=agenda&date=" + day,
                        "/calendar/new",
                        "/calendar/reminders",
                        "/resources",
                        "/resources/guide-13",
                        "/dashboard/preferences",
                    ]:
                        response = page.goto(origin + path)
                        assert response.status == 200, (width, path, response.status)
                        assert page.evaluate(
                            "document.documentElement.scrollWidth<=window.innerWidth+1"
                        ), (width, path, "horizontal overflow")
                        layouts += 1
                    if width == 390:
                        page.goto(origin)
                        page.screenshot(
                            path=str(artifact / "dashboard-mobile.png"), full_page=True
                        )
                        page.goto(origin + "/calendar?view=month&date=" + day)
                        page.screenshot(
                            path=str(artifact / "calendar-mobile.png"), full_page=True
                        )
                page.goto(origin + "/calendar/new")
                page.locator("#event-title").focus()
                page.keyboard.press("Tab")
                expect(page.locator("#event-start_date")).to_be_focused()
                page.emulate_media(reduced_motion="reduce")
                page.goto(origin + "/tour")
                assert page.evaluate(
                    'matchMedia("(prefers-reduced-motion: reduce)").matches'
                )
                checks.append(
                    "60 viewport/page checks, native keyboard focus and reduced-motion tour"
                )
                foreign = browser.new_page()
                foreign.goto(origin + "/auth/login")
                foreign.locator("#email").fill("fictional-unrelated@example.com")
                foreign.locator("#password").fill(PASSWORD)
                foreign.locator(".auth-submit").click()
                assert foreign.goto(event_url).status == 404
                foreign.goto(origin + "/resources?saved=1")
                assert "0 matching resources" in foreign.content()
                checks.append(
                    "Unrelated workspace cannot open event or inherit private bookmarks"
                )
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
    print(
        json.dumps(dict(checks=checks, viewport_pages=layouts, failures=[]), indent=2)
    )


if __name__ == "__main__":
    main()
