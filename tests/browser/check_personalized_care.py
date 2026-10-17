"""Fictional full personalization -> assigned care -> acknowledged handoff demo."""

import json, logging, sys, tempfile, threading, traceback, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from flask_migrate import upgrade
from flask import session
from flask_login import login_user
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from sqlalchemy import select
from olumira import create_app
from olumira.extensions import db
from olumira.models import WorkspaceMembership, CareProfile, User
from services.workspaces import resolve_context
from services import routine_builder
from services.observations import add_observation
from support import create_user, PASSWORD
from check_communication_boards import SPEECH_MOCK


def main():
    artifacts = ROOT / "artifacts" / "day27-28"
    artifacts.mkdir(parents=True, exist_ok=True)
    checks = []
    failures = []
    viewports = 0
    stage = "startup"
    with tempfile.TemporaryDirectory() as directory:
        app = create_app(
            {
                "APP_ENV": "testing",
                "DATABASE": str(Path(directory) / "care.db"),
                "AUTH_LOGIN_IP_LIMIT": "1000 per hour",
                "AUTH_LOGIN_ACCOUNT_LIMIT": "1000 per hour",
            }
        )
        with app.app_context():
            upgrade()
        owner, ws = create_user(app, "fictional-care-owner@example.com")
        helper, _ = create_user(app, "fictional-care-helper@example.com")
        viewer, _ = create_user(app, "fictional-care-viewer@example.com")
        other, _ = create_user(app, "fictional-care-other@example.com")
        profile = uuid.uuid4().hex
        second = uuid.uuid4().hex
        with app.app_context():
            db.session.add_all(
                [
                    CareProfile(
                        id=profile, workspace_id=ws, display_name="Fictional Fern"
                    ),
                    CareProfile(
                        id=second, workspace_id=ws, display_name="Fictional Willow"
                    ),
                ]
            )
            for uid, role in [(helper, "caregiver"), (viewer, "viewer")]:
                db.session.add(
                    WorkspaceMembership(
                        id=uuid.uuid4().hex,
                        workspace_id=ws,
                        user_id=uid,
                        role=role,
                        status="active",
                    )
                )
            db.session.commit()
            with app.test_request_context("/"):
                login_user(db.session.get(User, owner))
                session["workspace_id"] = ws
                session["profile_id"] = profile
                resolve_context()
                rid, _ = routine_builder.save(
                    dict(
                        name="Fictional story routine",
                        description="",
                        category="Morning",
                        icon="book",
                        color="sage",
                        profile_id=profile,
                        steps=[
                            dict(
                                id="",
                                title="Choose a woodland story",
                                description="",
                                icon="book",
                            )
                        ],
                    )
                )
                oid = add_observation(
                    ws,
                    "Fictional garden moment",
                    "2026-10-17",
                    "Private fictional observation marker",
                    "Calm",
                    "Fictional",
                )
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        app.config["PUBLIC_APP_URL"] = origin
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport=dict(width=1440, height=1000))
                context.add_init_script(SPEECH_MOCK)
                page = context.new_page()
                page.on(
                    "pageerror",
                    lambda error: failures.append("JavaScript runtime error"),
                )

                def login(page, email, shared=False, select_profile=True):
                    page.goto(origin + "/auth/login")
                    page.locator("#email").fill(email)
                    page.locator("#password").fill(PASSWORD)
                    page.locator(".auth-submit").click()
                    page.wait_for_url(origin + "/")
                    if shared:
                        page.locator("#active-workspace").select_option(ws)
                        page.get_by_role(
                            "button", name="Switch workspace", exact=True
                        ).click()
                    if select_profile:
                        page.locator("#active-profile").select_option(profile)
                        page.get_by_role(
                            "button", name="Switch profile", exact=True
                        ).click()

                login(page, "fictional-care-owner@example.com")
                stage = "Day 27 profile board and favorites"
                page.goto(origin + "/communication/new?template=words")
                page.locator("#board-title").fill("Fictional Fern’s words")
                page.locator("#save-board").click()
                page.wait_for_url("**/communication/*")
                board_url = page.url
                bid = board_url.rsplit("/", 1)[1]
                page.goto(origin + "/communication/phrases")
                page.locator("#phrase-label").fill("Water please")
                page.locator("#phrase-text").fill("I want water.")
                page.get_by_role("button", name="Save phrase", exact=True).click()
                page.goto(origin + "/communication/favorites/manage")
                page.get_by_role("button", name="Favorite picture", exact=True).nth(
                    0
                ).click()
                page.get_by_role("button", name="Favorite picture", exact=True).nth(
                    1
                ).click()
                page.locator(".workspace-grid section").first.locator(
                    ".favorite-row"
                ).last.get_by_role("button", name="Move picture up", exact=True).click()
                page.get_by_role("button", name="Favorite phrase", exact=True).click()
                assert (
                    page.locator(".workspace-grid section")
                    .first.locator(".favorite-row strong")
                    .first.inner_text()
                    == "want"
                )
                page.goto(origin + "/communication/settings")
                page.locator("#pref-card_size").select_option("large")
                page.locator("#pref-layout").select_option("2")
                page.locator("#pref-text_position").select_option("above")
                page.locator("[name=high_contrast]").check()
                page.locator("[name=reduced_motion]").check()
                page.locator("[name=simplified]").check()
                page.locator("#pref-default-board").select_option(bid)
                page.locator("#pref-speech-rate").select_option("0.8")
                page.locator("#pref-voice").fill("fiction-unavailable")
                assert (
                    page.locator("#preferences-preview")
                    .get_attribute("class")
                    .find("pref-size-large")
                    >= 0
                )
                page.get_by_role("button", name="Save preferences", exact=True).click()
                page.goto(origin + "/communication/open")
                page.wait_for_url(board_url)
                assert "pref-size-large" in page.locator(
                    "#communication-board"
                ).get_attribute("class")
                assert "simplified-board" in page.locator(
                    "#communication-board"
                ).get_attribute("class")
                assert page.locator("#save-phrase-open").is_hidden()
                assert (
                    page.locator("#communication-picture-grid")
                    .get_attribute("class")
                    .endswith("layout-2")
                )
                for label in ["I", "want", "water"]:
                    page.locator(f'[data-picture-card][data-label="{label}"]').click()
                assert page.locator("#phrase-written").inner_text() == "I want water"
                assert page.evaluate("window.__spoken.at(-1).rate") == 0.8
                page.locator("#simplified-toggle").click()
                assert page.locator("#phrase-written").inner_text() == "I want water"
                checks.append(
                    "Day 27: default board, reordered card/phrase favorites, live preview, large/high-contrast/reduced-motion layout, simplified controls and persisted speech rate"
                )
                stage = "Day 27 profile switching and another device"
                page.locator("#board-focus").click()
                page.locator("#active-profile").select_option(second)
                page.get_by_role("button", name="Switch profile", exact=True).click()
                page.wait_for_url(origin + "/communication")
                assert "Fictional Fern’s words" not in page.locator("main").inner_text()
                page.goto(origin + "/communication/favorites")
                assert page.locator("[data-picture-card]").count() == 0
                assert page.locator("[data-saved-phrase]").count() == 0
                page.locator("#board-focus").click()
                page.locator("#active-profile").select_option(profile)
                page.get_by_role("button", name="Switch profile", exact=True).click()
                page.wait_for_url(board_url)
                assert page.locator("#phrase-written").inner_text() == ""
                helper_ctx = browser.new_context()
                helper_ctx.add_init_script(SPEECH_MOCK)
                helper_page = helper_ctx.new_page()
                login(helper_page, "fictional-care-helper@example.com", True)
                helper_page.goto(origin + "/communication/open")
                helper_page.wait_for_url(board_url)
                assert "pref-size-large" in helper_page.locator(
                    "#communication-board"
                ).get_attribute("class")
                helper_page.locator('[data-picture-card][data-label="water"]').click()
                assert helper_page.evaluate("window.__spoken.at(-1).rate") == 0.8
                page.goto(origin + "/communication/favorites")
                assert page.locator("[data-picture-card]").first.inner_text() == "want"
                assert (
                    page.get_by_role("button", name="Water please", exact=True).count()
                    == 1
                )
                checks.append(
                    "Day 27: profile switch clears transient message and isolates boards/favorites/phrases; fresh caregiver browser receives server preferences"
                )
                stage = "Day 28 tasks assignment and routine integration"
                page.goto(origin + "/care/tasks/new")
                page.locator("#care-task-title").fill(
                    "Fictional prepare story materials"
                )
                page.locator("#care-task-description").fill(
                    "Prepare familiar picture cards before the story routine."
                )
                page.locator("#care-task-assignee").select_option(helper)
                page.locator("#care-task-due").fill("2030-10-22T08:00")
                page.locator("#care-task-routine").select_option(str(rid))
                page.get_by_role("button", name="Save task", exact=True).click()
                page.wait_for_url("**/care/tasks/*")
                task_url = page.url
                tid = task_url.rsplit("/", 1)[1]
                assert (
                    page.get_by_role(
                        "link", name="Open related routine", exact=False
                    ).count()
                    == 1
                )
                page.goto(task_url + "/edit")
                page.locator("#care-task-title").fill("Fictional retained task draft")
                helper_page.goto(origin + "/care/tasks?view=my")
                helper_page.get_by_role(
                    "link", name="Fictional prepare story materials", exact=True
                ).click()
                helper_page.get_by_role(
                    "button", name="Mark completed", exact=True
                ).click()
                expect(helper_page.locator("main")).to_contain_text("Completed")
                page.get_by_role("button", name="Save task", exact=True).click()
                expect(page.get_by_role("alert")).to_contain_text(
                    "Another caregiver changed"
                )
                assert (
                    page.locator("#care-task-title").input_value()
                    == "Fictional retained task draft"
                )
                page.goto(task_url + "/edit")
                page.locator("#care-task-title").fill(
                    "Fictional prepare story materials"
                )
                page.locator("#care-task-assignee").select_option(owner)
                page.get_by_role("button", name="Save task", exact=True).click()
                page.goto(origin + f"/routines/{rid}")
                page.get_by_role(
                    "button", name="Start or resume guided routine", exact=True
                ).click()
                page.get_by_role("button", name="Complete step", exact=True).click()
                expect(
                    page.get_by_role(
                        "heading", name="You did it, together.", exact=True
                    )
                ).to_be_visible()
                checks.append(
                    "Day 28: assigned task appears to caregiver, completion persists, stale edit retained, reassignment works and linked guided routine completes"
                )
                stage = "Day 28 handoff reference, acknowledgment, history and timeline"
                page.goto(origin + "/care/handoffs/new")
                page.locator("#handoff-recipient").select_option(helper)
                page.locator("#handoff-summary").fill(
                    "Fictional handoff: story materials are ready; review the linked garden observation."
                )
                page.locator(f'[name=task_ids][value="{tid}"]').check()
                page.locator("#handoff-routine").select_option(str(rid))
                page.locator("#handoff-observation").select_option(str(oid))
                page.get_by_role("button", name="Share handoff", exact=True).click()
                page.wait_for_url("**/care/handoffs/*")
                handoff_url = page.url
                assert (
                    page.get_by_role(
                        "button", name="Acknowledge handoff", exact=True
                    ).count()
                    == 0
                )
                helper_page.goto(origin + "/")
                expect(helper_page.locator("main")).to_contain_text(
                    "1 handoffs awaiting you"
                )
                helper_page.goto(handoff_url)
                helper_page.get_by_role(
                    "button", name="Acknowledge handoff", exact=True
                ).click()
                helper_page.reload()
                expect(helper_page.locator("main")).to_contain_text("Acknowledged")
                page.goto(origin + "/care/handoffs?status=acknowledged")
                assert (
                    page.get_by_role(
                        "link", name="Fictional handoff:", exact=False
                    ).count()
                    == 1
                )
                page.goto(origin + "/care/activity")
                expect(page.locator("main")).to_contain_text("Task completed")
                expect(page.locator("main")).to_contain_text("Handoff acknowledged")
                expect(page.locator("main")).to_contain_text("Guided routine completed")
                expect(page.locator("main")).to_contain_text("Observation added")
                assert (
                    "Private fictional observation marker"
                    not in page.locator("main").inner_text()
                )
                page.goto(handoff_url)
                page.get_by_role(
                    "link", name="Review linked observation privately", exact=True
                ).click()
                expect(page.locator("main")).to_contain_text(
                    "Private fictional observation marker"
                )
                checks.append(
                    "Day 28: recipient-only acknowledgment, linked task/routine/private observation, persisted history, real dashboard pending count and safe shared event timeline"
                )
                stage = "viewer and family isolation"
                viewer_ctx = browser.new_context()
                v = viewer_ctx.new_page()
                login(v, "fictional-care-viewer@example.com", True)
                assert v.goto(task_url).status == 200
                assert v.get_by_role("link", name="Edit task", exact=True).count() == 0
                assert v.goto(origin + "/care/tasks/new").status == 403
                assert v.goto(origin + "/communication/settings").status == 403
                assert v.goto(handoff_url).status == 200
                assert (
                    v.get_by_role(
                        "button", name="Acknowledge handoff", exact=True
                    ).count()
                    == 0
                )
                other_ctx = browser.new_context()
                outsider = other_ctx.new_page()
                login(outsider, "fictional-care-other@example.com", False, False)
                for url in [
                    board_url,
                    task_url,
                    handoff_url,
                    origin + f"/care/observations/{oid}",
                ]:
                    assert outsider.goto(url).status == 404
                checks.append(
                    "viewer may use/read without managing; unrelated family gets 404 for boards, tasks, handoffs and observations"
                )
                stage = "responsive/accessibility and native forms"
                routes = [
                    origin + "/communication/settings",
                    origin + "/communication/favorites/manage",
                    board_url,
                    origin + "/care/tasks",
                    origin + "/care/tasks/new",
                    task_url,
                    origin + "/care/handoffs/new",
                    handoff_url,
                    origin + "/care/handoffs",
                    origin + "/care/activity",
                    origin + "/",
                ]
                for width, height in [
                    (320, 900),
                    (390, 844),
                    (768, 1024),
                    (1024, 768),
                    (1440, 1000),
                ]:
                    page.set_viewport_size(dict(width=width, height=height))
                    for url in routes:
                        assert page.goto(url).status == 200
                        assert page.locator("h1").count() == 1
                        assert page.evaluate(
                            "document.documentElement.scrollWidth<=innerWidth+1"
                        ), f"Overflow {width}"
                        for field in page.locator(
                            "input:not([type=hidden]),select,textarea"
                        ).all():
                            if field.is_visible():
                                assert (
                                    field.get_attribute("aria-label")
                                    or field.get_attribute("id")
                                    and page.locator(
                                        f'label[for="{field.get_attribute("id")}"]'
                                    ).count()
                                    or field.evaluate("el=>!!el.closest('label')")
                                )
                        viewports += 1
                    page.goto(board_url)
                    page.screenshot(
                        path=str(artifacts / f"personalized-board-{width}.png"),
                        full_page=True,
                    )
                    page.goto(handoff_url)
                    page.screenshot(
                        path=str(artifacts / f"handoff-{width}.png"), full_page=True
                    )
                native_ctx = browser.new_context(
                    java_script_enabled=False, viewport=dict(width=390, height=844)
                )
                native_ctx.add_cookies(context.cookies())
                native = native_ctx.new_page()
                native.goto(origin + "/care/tasks/new")
                native.locator("#care-task-title").fill(
                    "Fictional native responsibility"
                )
                native.get_by_role("button", name="Save task", exact=True).click()
                expect(native.locator("h1")).to_have_text(
                    "Fictional native responsibility"
                )
                native.goto(origin + "/communication/settings")
                assert native.locator("#pref-card_size").input_value() == "large"
                touch_ctx = browser.new_context(
                    has_touch=True, is_mobile=True, viewport=dict(width=390, height=844)
                )
                touch_ctx.add_cookies(context.cookies())
                touch_ctx.add_init_script(SPEECH_MOCK)
                touch = touch_ctx.new_page()
                touch.goto(board_url)
                touch.locator('[data-picture-card][data-label="water"]').tap()
                expect(touch.locator("#phrase-written")).to_have_text("water")
                touch.locator("#simplified-toggle").tap()
                expect(touch.locator("#phrase-written")).to_have_text("water")
                checks.append(
                    "55 new page/viewport combinations, labeled controls/no overflow, native care/preference forms, touch simplified mode and message preservation"
                )
                browser.close()
        except Exception as error:
            print(
                type(error).__name__,
                [
                    (Path(f.filename).name, f.lineno)
                    for f in traceback.extract_tb(error.__traceback__)
                    if "check_personalized_care" in f.filename
                ],
            )
            print((str(error).splitlines() or [""])[0][:180])
            failures.append("Failed during " + stage)
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
        speech="Local voice browser API mocked",
    )
    (artifacts / "report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
