"""Day 40: populated feature pages at all six required widths and real preferences."""

import argparse, json, logging, sys, threading, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
import test_communication as fixture
import test_calendar as calendar_fixture
import test_care_coordination as care_fixture
import test_journal as journal_fixture
from support import PASSWORD, post

CONTRAST = r"""() => {
const rgb=v=>(v.match(/[\d.]+/g)||[]).map(Number), blend=(t,b)=>t.slice(0,3).map((v,i)=>v*(t[3]??1)+b[i]*(1-(t[3]??1)));
const bg=e=>!e?[255,255,255]:blend(rgb(getComputedStyle(e).backgroundColor),bg(e.parentElement));
const lum=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
return [...document.querySelectorAll('h1,h2,h3,p,label,summary,a,button,legend')].filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&!e.disabled&&e.innerText.trim()).flatMap(e=>{let s=getComputedStyle(e),b=bg(e),f=lum(blend(rgb(s.color),b)),back=lum(b),ratio=(Math.max(f,back)+.05)/(Math.min(f,back)+.05),large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700);return ratio+.01<(large?3:4.5)?[{tag:e.tagName,ratio}]:[]})
}"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day-40-2", action="store_true")
    args = parser.parse_args()
    widths = (
        [320, 390, 768, 1024, 1280, 1440]
        if args.day_40_2
        else [320, 375, 430, 768, 1024, 1440]
    )
    case = fixture.CommunicationTests()
    case.setUp()
    artifact = ROOT / (
        "artifacts/day40-2/matrix" if args.day_40_2 else "artifacts/day40/matrix"
    )
    artifact.mkdir(parents=True, exist_ok=True)
    try:
        case.app.config["TEMPLATES_AUTO_RELOAD"] = True
        board = post(case.client, "/communication/new", case.values()).location
        routine = post(
            case.client,
            "/routines/new",
            dict(
                name="Fictional woodland morning",
                description="A familiar three-step morning.",
                category="Morning",
                icon="leaf",
                color="sage",
                profile_id="",
                step_id=["", "", ""],
                step_title=["Choose clothes", "Share breakfast", "Read a book"],
                step_description=["Take your time.", "", ""],
                step_icon=["person", "sun", "book"],
            ),
        ).location
        rid = routine.rsplit("/", 1)[1]
        run = post(
            case.client, f"/routines/{rid}/start", dict(launch_key=uuid.uuid4().hex)
        ).location
        event = post(
            case.client, "/calendar/new", calendar_fixture.CalendarTests.values(case)
        ).location
        post(
            case.client,
            "/care/tasks/new",
            care_fixture.CareCoordinationTests.values(case, assigned_to=case.uid),
        )
        post(case.client, "/observations", journal_fixture.JournalTests.values(case))
        from sqlalchemy import select
        from olumira.extensions import db
        from olumira.models import Observation

        with case.app.app_context():
            oid = db.session.scalar(
                select(Observation.id).where(Observation.workspace_id == case.ws)
            )
        routes = [
            "/",
            "/routines",
            "/routines/new",
            routine,
            run,
            "/communication",
            board,
            board + "/edit",
            "/observations",
            "/observations/timeline",
            "/observations/insights",
            "/observations/reports",
            "/calendar",
            "/calendar?view=week",
            "/calendar?view=day",
            "/calendar?view=agenda",
            "/calendar/new",
            event,
            "/resources",
            "/settings",
            "/settings/privacy",
            "/settings/notifications",
            "/notifications",
            "/setup",
            "/tour",
            "/tour?step=3",
            "/auth/settings",
            "/care/tasks",
            "/care/handoffs",
            "/routines/calendar",
            "/routines/history",
            f"/observations/{oid}",
            f"/observations/{oid}/edit",
            "/resources/guide-01",
            "/dashboard/preferences",
            "/calendar/reminders",
            "/workspaces/settings",
        ]
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, case.app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        checks = 0
        failures = []
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(
                    viewport=dict(width=1440, height=1000), reduced_motion="reduce"
                )
                page = context.new_page()
                page.on(
                    "pageerror", lambda e: errors.append("JavaScript runtime error")
                )
                for width in widths:
                    page.set_viewport_size(dict(width=width, height=1000))
                    for route in ["/auth/login", "/auth/register"]:
                        assert page.goto(origin + route).status == 200
                        assert page.evaluate(
                            "document.documentElement.scrollWidth<=innerWidth+1"
                        ), (width, route)
                        checks += 1
                page.goto(origin + "/auth/login")
                page.locator("#email").fill("fiction-board@example.com")
                page.locator("#password").fill(PASSWORD)
                page.locator(".auth-submit").click()
                expect(page).to_have_url(origin + "/setup")
                page.goto(origin + "/")
                for width in widths:
                    page.set_viewport_size(dict(width=width, height=1000))
                    for index, route in enumerate(routes):
                        response = page.goto(origin + route)
                        if response.status != 200:
                            failures.append(
                                dict(width=width, route=route, status=response.status)
                            )
                            continue
                        if not page.evaluate(
                            "document.documentElement.scrollWidth<=innerWidth+1"
                        ):
                            failures.append(
                                dict(
                                    width=width,
                                    route=route,
                                    error="horizontal overflow",
                                )
                            )
                        if page.get_by_role("heading", level=1).count() != 1:
                            failures.append(
                                dict(width=width, route=route, error="main heading")
                            )
                        if width == 1440:
                            findings = page.evaluate(CONTRAST)
                            if findings:
                                failures.append(
                                    dict(width=width, route=route, contrast=findings)
                                )
                        if width in [375, 1440] and route in [
                            "/",
                            "/routines",
                            board,
                            "/calendar",
                            "/observations",
                            "/settings",
                            "/notifications",
                            "/setup",
                            "/tour",
                            "/tour?step=3",
                        ]:
                            page.screenshot(
                                path=str(artifact / f"page-{index}-{width}.png"),
                                full_page=True,
                            )
                        checks += 1
                for width in widths:
                    page.set_viewport_size(dict(width=width, height=1000))
                    page.goto(origin + "/")
                    for label in ["Account menu", "Notifications, 1 unread"]:
                        summary = page.get_by_label(label, exact=True)
                        summary.click()
                        panel = summary.locator("..").locator(".account-panel")
                        bounds = panel.bounding_box()
                        assert (
                            bounds
                            and bounds["x"] >= 0
                            and bounds["x"] + bounds["width"] <= width + 1
                        ), ("dropdown", width, label)
                        page.keyboard.press("Escape")
                        expect(summary).to_be_focused()
                    checks += 1
                # Dropdown and mobile-menu focus remain independently controlled.
                page.set_viewport_size(dict(width=375, height=1000))
                page.goto(origin + "/")
                page.get_by_role("button", name="Menu").click()
                expect(page.get_by_role("button", name="Menu")).to_have_attribute(
                    "aria-expanded", "true"
                )
                page.keyboard.press("Escape")
                expect(page.get_by_role("button", name="Menu")).to_be_focused()
                page.get_by_label("Account menu", exact=True).click()
                page.keyboard.press("Escape")
                expect(page.get_by_label("Account menu", exact=True)).to_be_focused()
                page.goto(origin + "/settings")
                page.get_by_label("Larger text", exact=True).check()
                page.get_by_label("Reduce motion", exact=True).check()
                page.get_by_label("Enhanced contrast", exact=True).check()
                page.get_by_label(
                    "Reduce shadows and visual effects", exact=True
                ).check()
                page.get_by_role(
                    "button", name="Save personal settings", exact=True
                ).click()
                for width in [320, 1440]:
                    page.set_viewport_size(dict(width=width, height=1000))
                    for route in [
                        "/",
                        "/settings",
                        board,
                        "/calendar",
                        "/settings/privacy",
                        "/notifications",
                    ]:
                        page.goto(origin + route)
                        assert page.evaluate(
                            "document.documentElement.scrollWidth<=innerWidth+1"
                        ), ("larger text", width, route)
                        expect(page.locator("html")).to_have_attribute(
                            "data-reduced-motion", "true"
                        )
                        if width == 1440:
                            findings = page.evaluate(CONTRAST)
                            if findings:
                                failures.append(
                                    dict(
                                        mode="accessibility",
                                        route=route,
                                        contrast=findings,
                                    )
                                )
                        checks += 1
                browser.close()
        finally:
            server.shutdown()
        report = dict(
            page_viewport_checks=checks,
            widths=widths,
            failures=failures,
            javascript_errors=errors,
        )
        (artifact / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
        assert not failures and not errors
    finally:
        case.tearDown()


if __name__ == "__main__":
    main()
