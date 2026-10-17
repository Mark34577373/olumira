"""Day 40.1 progressive disclosure, guidance and preference interactions."""

import logging
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from test_communication import CommunicationTests
from support import PASSWORD


def main():
    case = CommunicationTests()
    case.setUp()
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = make_server("127.0.0.1", 0, case.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport=dict(width=1440, height=1000))
            page = context.new_page()
            page.goto(origin + "/auth/login")
            page.locator("#email").fill("fiction-board@example.com")
            page.locator("#password").fill(PASSWORD)
            page.locator(".auth-submit").click()
            page.wait_for_url(origin + "/")
            banner = page.locator(".setup-compact")
            expect(banner).to_be_visible()
            banner.locator("[data-dismiss-setup]").click()
            expect(banner).to_be_hidden()
            expect(page.locator("#dashboard-welcome")).to_be_focused()
            page.reload()
            expect(banner).to_be_visible()
            page.goto(origin + "/observations")
            composer = page.locator("#observation-composer")
            expect(composer.locator("summary")).to_be_hidden()
            page.get_by_role("link", name="Capture your first moment").click()
            expect(composer).to_have_attribute("open", "")
            composer.locator("summary").click()
            page.get_by_role("link", name="Add observation", exact=True).click()
            expect(composer).to_have_attribute("open", "")
            expect(composer.locator("input:not([type=hidden])").first).to_be_focused()
            composer.locator("summary").click()
            expect(
                page.get_by_role("link", name="Add observation", exact=True)
            ).to_be_focused()
            # Native summary is still usable when scripts are unavailable.
            native = browser.new_context(
                java_script_enabled=False, storage_state=context.storage_state()
            )
            fallback = native.new_page()
            fallback.goto(origin + "/observations")
            expect(fallback.locator("#observation-composer summary")).to_be_visible()
            fallback.locator("#observation-composer summary").click()
            expect(fallback.locator("#observation-composer")).to_have_attribute(
                "open", ""
            )
            native.close()
            page.goto(origin + "/settings")
            status = page.locator("[data-preference-status]")
            checkbox = page.locator("input[name=reduced_motion]")
            checkbox.check()
            expect(status).to_have_text("Unsaved changes")
            checkbox.uncheck()
            expect(status).to_have_text("No unsaved changes.")
            checkbox.check()
            page.get_by_role("button", name="Save personal settings").click()
            expect(page.locator("input[name=reduced_motion]")).to_be_checked()
            expect(status).to_have_text("No unsaved changes.")
            page.goto(origin + "/calendar")
            expect(page.locator(".filter-disclosure")).not_to_have_attribute("open", "")
            page.set_viewport_size(dict(width=375, height=1000))
            expect(page.locator(".calendar-mobile-agenda")).to_be_visible()
            expect(page.locator(".calendar-month")).to_be_hidden()
            page.goto(origin + "/tour")
            page.get_by_role("link", name="Next", exact=True).click()
            assert "step=1" in page.url
            page.get_by_role("link", name="Previous", exact=True).click()
            assert "step=0" in page.url or page.url.endswith("/tour")
            browser.close()
        print(
            "8 refinement interaction groups passed (including no-JavaScript fallback)."
        )
    finally:
        server.shutdown()
        case.tearDown()


if __name__ == "__main__":
    main()
