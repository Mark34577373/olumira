"""Fictional full Day 23–24 workflow, collaboration, responsive and native controls."""

import json, logging, sys, tempfile, threading, traceback, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from flask_migrate import upgrade
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from sqlalchemy import select
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    WorkspaceMembership,
    CareProfile,
    RoutineSchedule,
    RoutineSession,
)
from support import create_user, PASSWORD


def main():
    artifacts = ROOT / "artifacts" / "day23-24"
    artifacts.mkdir(parents=True, exist_ok=True)
    checks = []
    failures = []
    stage = "startup"
    viewports = 0
    with tempfile.TemporaryDirectory() as directory:
        app = create_app(
            {
                "APP_ENV": "testing",
                "DATABASE": str(Path(directory) / "browser.db"),
                "AUTH_LOGIN_IP_LIMIT": "1000 per hour",
                "AUTH_LOGIN_ACCOUNT_LIMIT": "1000 per hour",
            }
        )
        with app.app_context():
            upgrade()
        owner, workspace = create_user(app, "fiction-guided-owner@example.com")
        helper, _ = create_user(app, "fiction-guided-helper@example.com")
        viewer, _ = create_user(app, "fiction-guided-viewer@example.com")
        outsider, _ = create_user(app, "fiction-guided-outsider@example.com")
        profile = uuid.uuid4().hex
        with app.app_context():
            db.session.add(
                CareProfile(
                    id=profile, workspace_id=workspace, display_name="Fictional Fern"
                )
            )
            for uid, role in [(helper, "caregiver"), (viewer, "viewer")]:
                db.session.add(
                    WorkspaceMembership(
                        id=uuid.uuid4().hex,
                        workspace_id=workspace,
                        user_id=uid,
                        role=role,
                        status="active",
                    )
                )
            db.session.commit()
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        app.config["PUBLIC_APP_URL"] = origin
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport={"width": 1440, "height": 1050})
                page = context.new_page()
                page.on(
                    "pageerror",
                    lambda error: failures.append(
                        "JavaScript runtime error: " + str(error).splitlines()[0][:160]
                    ),
                )

                def login(page, email, shared=False):
                    page.goto(origin + "/auth/login")
                    page.locator("#email").fill(email)
                    page.locator("#password").fill(PASSWORD)
                    page.locator(".auth-submit").click()
                    page.wait_for_url(origin + "/")
                    if shared:
                        page.locator("#active-workspace").select_option(workspace)
                        page.get_by_role(
                            "button", name="Switch workspace", exact=True
                        ).click()
                    page.locator("#active-profile").select_option(profile)
                    page.get_by_role(
                        "button", name="Switch profile", exact=True
                    ).click()

                login(page, "fiction-guided-owner@example.com")
                stage = "five-step profile routine"
                page.goto(origin + "/routines/new?template=morning")
                page.locator("#builder-name").fill("Fictional forest morning")
                assert page.locator("[name=step_title]").count() == 5
                last = page.locator("[data-step-editor]").last
                moved_title = last.locator("[name=step_title]").input_value()
                last.locator("[data-step-up]").focus()
                page.keyboard.press("Enter")
                page.locator("#save-routine").click()
                page.wait_for_url("**/routines/*")
                sequence_url = page.url
                rid = int(sequence_url.rsplit("/", 1)[1])
                assert (
                    page.locator(".routine-sequence-list h3").nth(3).inner_text()
                    == moved_title
                )
                checks.append(
                    "profile-specific five-step routine and keyboard reorder persisted"
                )
                stage = "schedule creation and preview"
                page.get_by_role("link", name="Schedule routine").click()
                schedule_url = page.url
                start = datetime.now(timezone.utc).date() + timedelta(days=1)
                while start.weekday() > 4:
                    start += timedelta(days=1)
                page.locator("#schedule-date").fill(start.isoformat())
                page.locator("#schedule-time").fill("07:15")
                page.locator("#schedule-zone").fill("UTC")
                page.locator("#schedule-repeat").select_option("weekdays")
                for day in ["0", "1", "2", "3", "4"]:
                    page.locator(f'.weekday-choices input[value="{day}"]').check()
                assert (
                    "Mon, Tue, Wed, Thu, Fri at 07:15"
                    in page.locator("[data-schedule-summary]").inner_text()
                )
                page.get_by_role("button", name="Save schedule", exact=True).click()
                page.wait_for_url("**/routines/calendar*")
                calendar_url = (
                    origin
                    + f"/routines/calendar?date={start.isoformat()}&timezone=UTC&view=week"
                )
                page.goto(calendar_url)
                assert (
                    page.locator(".calendar-entry h3")
                    .filter(has_text="Fictional forest morning")
                    .count()
                    >= 5
                )
                checks.append(
                    "weekday schedule, human-readable live preview and actual weekly occurrences"
                )
                stage = "daily launch and desired step state"
                daily_url = calendar_url.replace("view=week", "view=day")
                page.goto(daily_url)
                page.get_by_role("button", name="Start routine", exact=True).click()
                page.wait_for_url("**/routines/sessions/*")
                player_url = page.url
                sid = player_url.rsplit("/", 1)[1]
                assert "0 of 5" in page.locator(".player-progress").inner_text()
                first_step_title = page.locator(".guided-step h2").inner_text()
                page.get_by_role("button", name="Complete step", exact=True).focus()
                page.keyboard.press("Enter")
                page.get_by_role("link", name="Previous step", exact=False).click()
                page.get_by_role("button", name="Undo this step", exact=True).click()
                assert "0 of 5" in page.locator(".player-progress").inner_text()
                page.get_by_role("button", name="Complete step", exact=True).click()
                page.get_by_role("button", name="Complete step", exact=True).click()
                page.get_by_role("button", name="Complete step", exact=True).click()
                assert "3 of 5" in page.locator(".player-progress").inner_text()
                page.get_by_role("link", name="Overview", exact=True).click()
                assert page.locator(".player-overview li").count() == 5
                assert "3 of 5" in page.locator(".player-progress").inner_text()
                checks.append(
                    "scheduled launch, keyboard completion, undo, automatic next step and overview preserve 3/5"
                )
                stage = "pause persistence and caregiver collaboration"
                page.get_by_role("button", name="Pause routine", exact=True).click()
                page.reload()
                assert "Take all the time you need" in page.locator("main").inner_text()
                paused_url = page.url
                helper_context = browser.new_context()
                helper_page = helper_context.new_page()
                login(helper_page, "fiction-guided-helper@example.com", True)
                helper_page.goto(player_url)
                assert (
                    helper_page.get_by_role(
                        "button", name="Resume routine", exact=True
                    ).count()
                    == 1
                )
                helper_page.get_by_role(
                    "button", name="Resume routine", exact=True
                ).click()
                page.bring_to_front()
                page.locator("#shared-run-update").wait_for(
                    state="visible", timeout=16000
                )
                page.get_by_role(
                    "link", name="Refresh saved progress", exact=True
                ).click()
                assert (
                    page.get_by_role("button", name="Pause routine", exact=True).count()
                    == 1
                )
                assert "3 of 5" in page.locator(".player-progress").inner_text()
                checks.append(
                    "pause survives reload; second caregiver resumes; live version notification preserves focus"
                )
                stage = "stale form collision"
                # Both forms carry the same version. Owner's action makes helper's form stale.
                page.get_by_role("link", name="Guided", exact=True).click()
                page.get_by_role("button", name="Complete step", exact=True).click()
                helper_page.get_by_role(
                    "button", name="Complete step", exact=True
                ).click()
                assert (
                    "Another caregiver updated"
                    in helper_page.locator("[role=alert]").inner_text()
                )
                assert "4 of 5" in helper_page.locator(".player-progress").inner_text()
                helper_page.get_by_role("link", name="Next step", exact=False).click()
                helper_page.get_by_role(
                    "button", name="Complete step", exact=True
                ).click()
                assert (
                    helper_page.get_by_role(
                        "heading", name="You did it, together.", exact=True
                    ).count()
                    == 1
                )
                page.goto(player_url)
                assert "5 of 5" in page.locator(".player-progress").inner_text()
                assert page.get_by_role("button", name="Undo", exact=False).count() == 0
                page.get_by_text(
                    "Saved run details & caregiver activity", exact=True
                ).click()
                assert "Completed a step" in page.locator(".run-activity").inner_text()
                checks.append(
                    "stale caregiver form rejected safely; final completion saved once with attribution"
                )
                stage = "history, filtering and schedule controls"
                page.goto(origin + "/routines/history?status=completed&timezone=UTC")
                assert (
                    page.get_by_role(
                        "link", name="View completed run", exact=False
                    ).count()
                    == 1
                )
                history_url = page.url
                page.locator("#history-status").select_option("paused")
                page.get_by_role("button", name="Filter history", exact=True).click()
                assert "No runs match" in page.locator("main").inner_text()
                page.goto(daily_url)
                assert "Completed" in page.locator(".calendar-column").inner_text()
                assert "5 of 5 steps" in page.locator(".calendar-column").inner_text()
                page.get_by_role("button", name="Pause", exact=True).click()
                assert (
                    page.get_by_role("button", name="Resume", exact=True).count() == 1
                )
                page.get_by_role("button", name="Resume", exact=True).click()
                assert page.get_by_role("button", name="Pause", exact=True).count() == 1
                checks.append(
                    "completed calendar progress, history filters and pause/resume schedule controls"
                )
                stage = "history snapshots after template edit"
                page.goto(origin + f"/routines/{rid}/builder")
                page.locator("#builder-name").fill("Fictional edited forest morning")
                page.locator("[name=step_title]").first.fill("Fictional changed step")
                page.locator("#save-routine").click()
                page.goto(player_url)
                assert (
                    page.get_by_role(
                        "heading", name="Fictional forest morning", exact=True
                    ).count()
                    == 1
                )
                assert first_step_title in page.locator(".player-overview").inner_text()
                checks.append(
                    "finished run keeps original title, ordered steps and completed progress after template edits"
                )
                stage = "viewer and unrelated family"
                viewer_context = browser.new_context()
                viewer_page = viewer_context.new_page()
                login(viewer_page, "fiction-guided-viewer@example.com", True)
                viewer_page.goto(player_url)
                assert "5 of 5" in viewer_page.locator(".player-progress").inner_text()
                assert viewer_page.locator("[data-run-action]").count() == 0
                viewer_page.goto(daily_url)
                assert (
                    viewer_page.get_by_role(
                        "link", name="Edit schedule", exact=True
                    ).count()
                    == 0
                )
                outsider_context = browser.new_context()
                outsider_page = outsider_context.new_page()
                outsider_page.goto(origin + "/auth/login")
                outsider_page.locator("#email").fill(
                    "fiction-guided-outsider@example.com"
                )
                outsider_page.locator("#password").fill(PASSWORD)
                outsider_page.locator(".auth-submit").click()
                outsider_page.wait_for_url(origin + "/")
                assert outsider_page.goto(player_url).status == 404
                assert (
                    "Fictional forest morning"
                    not in outsider_page.goto(origin + "/routines/history").text()
                )
                checks.append(
                    "viewer sees history without controls; unrelated workspace gets 404 and empty history"
                )
                stage = "native no-JavaScript controls"
                nojs = browser.new_context(
                    java_script_enabled=False, viewport={"width": 390, "height": 844}
                )
                nojs.add_cookies(context.cookies())
                native = nojs.new_page()
                native.goto(sequence_url)
                native.get_by_role(
                    "button", name="Start or resume guided routine", exact=True
                ).click()
                active_url = native.url
                native.get_by_role("button", name="Complete step", exact=True).click()
                native.get_by_role("button", name="Pause routine", exact=True).click()
                native.reload()
                assert "1 of 5" in native.locator(".player-progress").inner_text()
                native.get_by_role("button", name="Resume routine", exact=True).click()
                native.get_by_role("link", name="Overview", exact=True).click()
                assert native.locator(".player-overview li").count() == 5
                native.goto(schedule_url)
                assert native.locator("#schedule-repeat").count() == 1
                checks.append(
                    "no-JavaScript start, complete, pause, reload, resume, overview and scheduling form"
                )
                stage = "responsive, labels, keyboard focus and screenshots"
                paths = [
                    calendar_url,
                    daily_url,
                    schedule_url,
                    active_url,
                    active_url + "?mode=overview",
                    player_url,
                    history_url,
                    origin + "/",
                ]
                for width in [320, 375, 390, 768, 1024, 1440]:
                    page.set_viewport_size({"width": width, "height": 1000})
                    for url in paths:
                        page.goto(url)
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth+1"
                        ), f"overflow {width}"
                        assert (
                            page.locator(".site-header nav")
                            .locator("a[href='/routines']")
                            .count()
                            == 1
                        )
                        for control in page.locator(
                            "main input:not([type=hidden]),main select"
                        ).all():
                            assert (
                                control.get_attribute("aria-label")
                                or control.get_attribute("id")
                                and page.locator(
                                    f'label[for="{control.get_attribute("id")}"]'
                                ).count()
                                or control.evaluate("el=>!!el.closest('label')")
                            )
                        if width == 1440:
                            low = page.evaluate(r"""() => {
                                const rgb=v=>(v.match(/[\d.]+/g)||[]).map(Number),blend=(t,b)=>t.slice(0,3).map((v,i)=>v*(t[3]??1)+b[i]*(1-(t[3]??1)));
                                const bg=e=>!e?[255,255,255]:blend(rgb(getComputedStyle(e).backgroundColor),bg(e.parentElement));
                                const lum=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
                                return [...document.querySelectorAll('h1,h2,h3,p,label,summary,button,.text-link')].filter(e=>e.getClientRects().length&&!e.disabled).flatMap(e=>{const s=getComputedStyle(e),b=bg(e),f=lum(blend(rgb(s.color),b)),l=lum(b),r=(Math.max(f,l)+.05)/(Math.min(f,l)+.05),large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700);return r+.01<(large?3:4.5)?[e.tagName+'.'+e.className]:[];});
                            }""")
                            assert not low, "Contrast: " + ",".join(low)
                        viewports += 1
                    page.goto(active_url)
                    page.screenshot(
                        path=str(artifacts / f"guided-{width}.png"), full_page=True
                    )
                    page.goto(calendar_url)
                    page.screenshot(
                        path=str(artifacts / f"calendar-{width}.png"), full_page=True
                    )
                checks.append(
                    "48 page/viewport combinations: 320–1440px, no horizontal overflow, labels, main navigation and sampled text contrast"
                )
                page.goto(active_url)
                page.keyboard.press("Tab")
                assert page.evaluate("document.activeElement !== document.body")
                page.emulate_media(reduced_motion="reduce")
                assert page.evaluate(
                    'matchMedia("(prefers-reduced-motion: reduce)").matches'
                )
                checks.append("keyboard focus and reduced-motion preference")
                stage = "mobile touch"
                touch = browser.new_context(
                    has_touch=True,
                    is_mobile=True,
                    viewport={"width": 390, "height": 844},
                )
                touch.add_cookies(context.cookies())
                mobile = touch.new_page()
                mobile.goto(active_url)
                mobile.get_by_role("button", name="Pause routine", exact=True).tap()
                mobile.get_by_role("button", name="Resume routine", exact=True).tap()
                mobile.get_by_role("link", name="Overview", exact=True).tap()
                mobile.locator(".player-overview li").first.wait_for(state="visible")
                assert mobile.locator(".player-overview li").count() == 5
                checks.append("touch pause, resume and mode switch")
                browser.close()
        except Exception as error:
            print(
                type(error).__name__,
                [
                    (Path(f.filename).name, f.lineno)
                    for f in traceback.extract_tb(error.__traceback__)
                    if "check_guided_routines" in f.filename
                ],
            )
            print(
                "Diagnostic",
                (str(error).splitlines() or [type(error).__name__])[0][:200],
            )
            failures.append("Browser validation failed during " + stage)
        finally:
            server.shutdown()
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
    result = dict(
        checks=checks,
        failures=failures,
        viewport_combinations=viewports,
        fictional_data_only=True,
    )
    (artifacts / "report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
