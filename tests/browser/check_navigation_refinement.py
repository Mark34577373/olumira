"""Day 40.2 secure context switching through real native forms, with and without JS."""

import json
import logging
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
import test_workspaces as fixture
from support import PASSWORD, post


def main():
    case = fixture.WorkspaceTests()
    case.setUp()
    server = None
    try:
        pid = case.profile("Fictional Fern")
        post(case.client, "/workspaces/create", dict(name="Fictional Maple Family"))
        with case.client.session_transaction() as session:
            maple = session["workspace_id"]
        maple_pid = case.profile("Fictional Maple Profile")
        post(case.client, "/workspaces/select", dict(workspace_id=case.workspace))
        case.app.config["TEMPLATES_AUTO_RELOAD"] = True
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, case.app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        out = ROOT / "artifacts/day40-2/navigation"
        out.mkdir(parents=True, exist_ok=True)
        errors = []
        layouts = 0
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport=dict(width=1440, height=1000))
            page = context.new_page()
            page.on("pageerror", lambda e: errors.append("JavaScript error"))
            page.goto(origin + "/auth/login")
            page.locator("#email").fill("owner-fiction@example.com")
            page.locator("#password").fill(PASSWORD)
            page.locator(".auth-submit").click()
            page.wait_for_url(origin + "/")
            expect(page.locator("#active-workspace option")).to_have_count(2)
            assert (
                case.other_workspace
                not in page.locator("#active-workspace").inner_html()
            )
            page.locator("#active-workspace").select_option(maple)
            # Selection alone does not submit or change the profile list.
            assert page.url == origin + "/"
            page.get_by_role("button", name="Switch workspace", exact=True).click()
            expect(page.locator("#active-workspace")).to_have_value(maple)
            expect(page.locator("#active-profile")).to_have_value("")
            expect(
                page.get_by_text(
                    "Workspace switched. Workspace-wide care is active.", exact=True
                )
            ).to_be_visible()
            assert pid not in page.locator("#active-profile").inner_html()
            page.locator("#active-profile").select_option(maple_pid)
            page.get_by_role("button", name="Switch profile", exact=True).click()
            expect(page.locator("#active-profile")).to_have_value(maple_pid)
            csrf = page.locator(
                ".workspace-inline input[name=csrf_token]"
            ).first.input_value()
            for path, values in [
                ("/workspaces/select", dict(workspace_id=case.other_workspace)),
                ("/workspaces/profiles/select", dict(profile_id=pid)),
            ]:
                response = page.request.post(
                    origin + path, form=dict(csrf_token=csrf, **values), max_redirects=0
                )
                assert response.status == 404
            page.reload()
            expect(page.locator("#active-workspace")).to_have_value(maple)
            expect(page.locator("#active-profile")).to_have_value(maple_pid)
            page.goto(origin + "/calendar")
            expect(page.locator(".site-header")).to_be_visible()
            page.locator("#active-profile").select_option("")
            page.get_by_role("button", name="Switch profile", exact=True).click()
            page.wait_for_url(origin + "/calendar")
            expect(page.locator("#active-profile")).to_have_value("")
            account = page.locator(".account-menu:not(.notification-menu)")
            account.locator("summary").click()
            account.get_by_role("link", name="My account", exact=True).click()
            page.wait_for_url(origin + "/auth/settings")
            expect(
                page.get_by_role("heading", name="Account & security", exact=True)
            ).to_be_visible()
            expect(page.locator(".settings-sections [aria-current=page]")).to_have_text(
                "Account & security"
            )
            page.locator(".settings-sections").get_by_role(
                "link", name="Appearance & accessibility"
            ).click()
            expect(
                page.get_by_role("heading", name="Preferences", exact=True)
            ).to_be_visible()
            for width in [1440, 1280, 1024, 768, 390, 320]:
                page.set_viewport_size(dict(width=width, height=1000))
                for route in [
                    "/",
                    "/auth/settings",
                    "/settings",
                    "/care/tasks",
                    "/calendar",
                    "/routines",
                    "/care/activity",
                ]:
                    assert page.goto(origin + route).status == 200
                    assert page.evaluate(
                        "document.documentElement.scrollWidth<=innerWidth+1"
                    ), (width, route)
                    expect(page.locator(".site-header")).to_be_visible()
                    expect(page.locator("#active-workspace")).to_be_visible()
                    if route in ["/auth/settings", "/settings"] and width <= 700:
                        assert page.locator(".settings-sections").evaluate(
                            '(n)=>{const a=n.querySelector("[aria-current]").getBoundingClientRect(),b=n.getBoundingClientRect();return a.left>=b.left-1&&a.right<=b.right+1}'
                        ), ("active section visible", width, route)
                    if width == 320:
                        positions = page.locator(
                            ".site-header .account-menu summary"
                        ).evaluate_all(
                            "(rows)=>rows.map(e=>e.getBoundingClientRect().top)"
                        )
                        assert (
                            max(positions) - min(positions) <= 2
                        ), "narrow header controls stay on one row"
                    expect(
                        page.get_by_role("button", name="Switch profile", exact=True)
                    ).to_be_visible()
                    layouts += 1
                if width == 320:
                    page.get_by_role("button", name="Menu").click()
                    expect(page.locator("#primary-links")).to_be_visible()
                    page.keyboard.press("Escape")
                    expect(page.locator("#primary-links")).to_be_hidden()
            native = browser.new_context(
                java_script_enabled=False, storage_state=context.storage_state()
            )
            fallback = native.new_page()
            fallback.goto(origin + "/")
            fallback.locator("#active-workspace").select_option(case.workspace)
            fallback.get_by_role("button", name="Switch workspace", exact=True).click()
            expect(fallback.locator("#active-workspace")).to_have_value(case.workspace)
            expect(fallback.locator("#active-profile")).to_have_value("")
            expect(
                fallback.locator(f'#active-profile option[value="{pid}"]')
            ).to_have_count(1)
            native.close()
            assert not errors
            browser.close()
        report = dict(
            workflows="Explicit POST context switching, unauthorized/foreign rejection, workspace-wide reset, account/preferences links, calendar shell, mobile menu, no-JavaScript fallback",
            viewport_visits=layouts,
            widths=[1440, 1280, 1024, 768, 390, 320],
            javascript_errors=errors,
        )
        (out / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
    finally:
        if server:
            server.shutdown()
        case.tearDown()


if __name__ == "__main__":
    main()
