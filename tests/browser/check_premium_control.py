"""Repeatable fictional Days 37–39 user journey with actual forms and downloads."""

import json, logging, sys, tempfile, threading, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from flask_migrate import upgrade
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from olumira import create_app
from olumira.extensions import db
from olumira.models import CareProfile, CalendarEvent, utcnow
from support import PASSWORD, create_user


def main():
    artifacts = ROOT / "artifacts/day37-39"
    artifacts.mkdir(parents=True, exist_ok=True)
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
        uid, wid = create_user(app, "fictional-premium@example.com")
        other, foreign = create_user(app, "fictional-unrelated-premium@example.com")
        pid = uuid.uuid4().hex
        eid = uuid.uuid4().hex
        with app.app_context():
            db.session.add(
                CareProfile(id=pid, workspace_id=wid, display_name="Fictional Fern")
            )
            db.session.add(
                CalendarEvent(
                    id=eid,
                    workspace_id=foreign,
                    title="Unrelated private event",
                    start_date="2030-01-01",
                    end_date="2030-01-01",
                    local_time="09:00",
                    end_time="10:00",
                    timezone="UTC",
                    created_by=other,
                )
            )
            db.session.commit()
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(
                    viewport=dict(width=1440, height=1000),
                    reduced_motion="reduce",
                    accept_downloads=True,
                )
                page = context.new_page()
                errors = []
                page.on(
                    "pageerror", lambda error: errors.append("JavaScript runtime error")
                )

                def signin():
                    page.goto(origin + "/auth/login")
                    page.locator("#email").fill("fictional-premium@example.com")
                    page.locator("#password").fill(PASSWORD)
                    page.locator(".auth-submit").click()
                    expect(page).to_have_url(origin + "/")

                signin()
                page.goto(origin + "/settings")
                page.get_by_label("Reduce motion", exact=True).check()
                page.get_by_label(
                    "Reduce shadows and visual effects", exact=True
                ).check()
                page.get_by_label("Larger text", exact=True).check()
                page.get_by_label("Enhanced contrast", exact=True).check()
                page.get_by_label("Simplify decorative details", exact=True).check()
                page.get_by_label("Default calendar view").select_option("week")
                page.get_by_label("Week begins").select_option("sunday")
                page.get_by_label("Calendar clock").select_option("12")
                page.get_by_role(
                    "button", name="Save personal settings", exact=True
                ).click()
                page.reload()
                expect(page.locator("html")).to_have_attribute(
                    "data-reduced-motion", "true"
                )
                expect(page.get_by_label("Default calendar view")).to_have_value("week")
                assert (
                    page.locator("html").evaluate("(el)=>getComputedStyle(el).fontSize")
                    == "19.2px"
                )
                page.goto(origin + "/dashboard/preferences")
                page.get_by_label("Preferred care profile").select_option(pid)
                page.get_by_role(
                    "button", name="Save dashboard preferences", exact=True
                ).click()
                page.goto(origin + "/dashboard/preferences")
                expect(page.get_by_label("Preferred care profile")).to_have_value(pid)
                page.get_by_role(
                    "button", name="Open my preferred profile", exact=True
                ).click()
                expect(page.locator("#active-profile")).to_have_value(pid)
                page.goto(origin + "/care/tasks/new")
                page.get_by_label("Task title", exact=True).fill(
                    "Fictional prepare garden cards"
                )
                page.get_by_label("Helpful details (optional)", exact=True).fill(
                    "Fictional private detail excluded from notification previews"
                )
                page.get_by_label("Assigned caregiver", exact=True).select_option(uid)
                page.get_by_role("button", name="Save task", exact=True).click()
                page.goto(origin + "/notifications")
                expect(
                    page.get_by_role(
                        "heading",
                        name="A caregiver task was assigned to you",
                        exact=True,
                    )
                ).to_be_visible()
                assert (
                    "Fictional private detail" not in page.locator("main").inner_text()
                )
                page.get_by_role("button", name="Mark read", exact=True).click()
                expect(page.locator("main")).to_contain_text("Read")
                page.goto(origin + "/calendar/reminders")
                page.locator('input[name="enabled"]').check()
                page.locator('select[name="lead_minutes"]').select_option("15")
                page.get_by_role(
                    "button", name="Save reminder preferences", exact=True
                ).click()
                page.goto(origin + "/settings/privacy")
                form = page.locator("form").filter(
                    has=page.get_by_role(
                        "button", name="Prepare secure export", exact=True
                    )
                )
                form.get_by_label("Current password", exact=True).fill(PASSWORD)
                form.get_by_role(
                    "button", name="Prepare secure export", exact=True
                ).click()
                with page.expect_download() as download_info:
                    page.get_by_role(
                        "button", name="Download JSON export", exact=True
                    ).click()
                download = download_info.value
                payload = json.loads(Path(download.path()).read_text())
                assert payload["account"]["email"] == "fictional-premium@example.com"
                assert "routines" not in payload["records"]
                page.get_by_text("Review account deletion", exact=True).click()
                page.get_by_text("Review workspace closure", exact=True).click()
                # Review only: never submit destructive forms in the browser demo.
                page.goto(origin + "/auth/settings")
                page.locator(".account-menu").filter(
                    has=page.get_by_label("Account menu", exact=True)
                ).locator("summary").click()
                page.get_by_role("button", name="Sign out", exact=True).click()
                signin()
                page.goto(origin + "/settings")
                expect(page.get_by_label("Reduce motion", exact=True)).to_be_checked()
                expect(page.get_by_label("Default calendar view")).to_have_value("week")
                assert page.goto(origin + "/calendar/" + eid).status == 404
                routes = [
                    "/settings",
                    "/settings/notifications",
                    "/settings/privacy",
                    "/notifications",
                    "/calendar",
                    "/dashboard/preferences",
                ]
                for width in [320, 390, 768, 1024, 1440]:
                    page.set_viewport_size(dict(width=width, height=1000))
                    for route in routes:
                        response = page.goto(origin + route)
                        assert response.status == 200, (route, response.status)
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth+1"
                        ), (width, route)
                        assert page.get_by_role("heading", level=1).count() == 1
                        layouts += 1
                    if width in [390, 1440]:
                        page.goto(origin + "/settings")
                        page.screenshot(
                            path=str(artifacts / f"settings-{width}.png"),
                            full_page=True,
                        )
                page.goto(origin + "/settings")
                page.keyboard.press("Tab")
                expect(page.locator(".skip-link")).to_be_focused()
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
    print(
        json.dumps(
            dict(
                journey="Settings → default profile → real task notification → read → reminder timing → private export → review closure → logout/login persistence → unrelated-workspace denial",
                layouts=layouts,
                javascript_errors=0,
            )
        )
    )


if __name__ == "__main__":
    main()
