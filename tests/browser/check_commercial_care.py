"""Fictional end-to-end care plan, studio, handoff and viewport acceptance."""

import json, logging, sys, tempfile, threading, re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from flask_migrate import upgrade
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from sqlalchemy import select, func
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    CareProfile,
    WorkspaceMembership,
    Observation,
    RoutineSession,
    RoutineSessionStep,
)
from support import create_user, PASSWORD


def main():
    out = ROOT / "artifacts/day43-5"
    out.mkdir(parents=True, exist_ok=True)
    checks = []
    errors = []
    stage = "setup"
    with tempfile.TemporaryDirectory(prefix="olumira-commercial-") as folder:
        app = create_app(
            dict(
                APP_ENV="testing",
                DATABASE=str(Path(folder) / "fictional.db"),
                AUTH_LOGIN_IP_LIMIT="1000 per hour",
                AUTH_LOGIN_ACCOUNT_LIMIT="1000 per hour",
            )
        )
        with app.app_context():
            upgrade()
        owner, workspace = create_user(app, "commercial-owner@example.com")
        helper, _ = create_user(app, "commercial-helper@example.com")
        outsider, _ = create_user(app, "commercial-outsider@example.com")
        profile = "b" * 32
        with app.app_context():
            db.session.add(
                WorkspaceMembership(
                    id="a" * 32,
                    workspace_id=workspace,
                    user_id=helper,
                    role="caregiver",
                    status="active",
                )
            )
            db.session.add(
                CareProfile(
                    id=profile,
                    workspace_id=workspace,
                    display_name="Fictional Fern",
                    communication="Offer familiar picture choices.",
                )
            )
            db.session.commit()
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        app.config["PUBLIC_APP_URL"] = origin
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                ctx = browser.new_context(viewport=dict(width=1440, height=1000))
                page = ctx.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("dialog", lambda dialog: dialog.accept())

                def login(page, email):
                    page.goto(origin + "/auth/login")
                    page.locator("#email").fill(email)
                    page.locator("#password").fill(PASSWORD)
                    page.locator(".auth-submit").click()
                    page.wait_for_url(origin + "/")

                def select_profile(page):
                    page.locator("#active-profile").select_option(profile)
                    page.get_by_role(
                        "button", name="Switch profile", exact=True
                    ).click()
                    page.wait_for_url(origin + "/")

                login(page, "commercial-owner@example.com")
                select_profile(page)
                stage = "care plan wizard"
                page.goto(origin + "/care-plans/new")
                page.locator("#plan-title").fill("Fictional familiar day")
                for _ in range(4):
                    page.locator("[data-wizard-next]").click()
                page.locator("#plan-goal").fill("Make the day familiar")
                page.locator("[data-wizard-next]").click()
                expect(page.locator("[data-plan-review]")).to_contain_text(
                    "Make the day familiar"
                )
                page.get_by_role("button", name="Save care plan", exact=True).click()
                page.wait_for_url(re.compile(r".*/care-plans/[a-f0-9]{32}$"))
                plan_url = page.url
                expect(page.locator("main")).to_contain_text("Make the day familiar")
                checks.append("Guided plan and first goal saved")
                stage = "visual studio"
                page.clock.install()
                page.goto(origin + "/routines/new?template=communication")
                page.locator("#builder-name").fill("Fictional picture rhythm")
                expect(page.locator("[data-step-editor]")).to_have_count(4)
                page.locator("[data-step-duplicate]").first.click()
                expect(page.locator("[data-step-editor]")).to_have_count(5)
                page.locator("[data-step-undo]").click()
                expect(page.locator("[data-step-editor]")).to_have_count(4)
                first_title = page.locator("[name=step_title]").first.input_value()
                page.locator("[data-step-down]").first.click()
                assert (
                    page.locator("[name=step_title]").nth(1).input_value()
                    == first_title
                )
                page.locator("[data-step-editor] details").first.locator(
                    "summary"
                ).click()
                page.locator("[name=step_timer_seconds]").first.fill("1")
                page.locator("#preview-steps [data-timer-action=start]").first.click()
                page.locator("#preview-steps [data-timer-action=pause]").first.click()
                paused = page.locator(
                    "#preview-steps [data-timer-output]"
                ).first.inner_text()
                page.clock.fast_forward(5000)
                expect(
                    page.locator("#preview-steps [data-timer-output]").first
                ).to_have_text(paused)
                page.locator("#preview-steps [data-timer-action=start]").first.click()
                page.clock.fast_forward(2000)
                expect(
                    page.locator("#preview-steps [data-timer-status]").first
                ).to_contain_text("finished")
                page.locator("#preview-steps [data-timer-action=reset]").first.click()
                expect(
                    page.locator("#preview-steps [data-timer-output]").first
                ).to_have_text("1s")
                page.locator("#preview-steps button").filter(
                    has_text="Preview: mark complete"
                ).first.click()
                assert page.locator("#preview-progress").get_attribute("value") == "1"
                with app.app_context():
                    assert (
                        db.session.scalar(
                            select(func.count()).select_from(RoutineSession)
                        )
                        == 0
                    )
                page.locator("#save-routine").click()
                page.wait_for_url(re.compile(r".*/routines/\d+$"))
                routine_url = page.url
                checks.append(
                    "Template, duplicate/undo, reorder, optional timer, local preview and save"
                )
                stage = "plan connections"
                rid = routine_url.rsplit("/", 1)[1]
                page.goto(plan_url + "/edit")
                page.locator("[data-wizard-next]").click()
                page.locator(f'input[name=routine_ids][value="{rid}"]').check()
                for _ in range(4):
                    page.locator("[data-wizard-next]").click()
                page.get_by_role("button", name="Save care plan", exact=True).click()
                page.wait_for_url(plan_url)
                expect(page.locator("main")).to_contain_text("Fictional picture rhythm")
                checks.append("Existing routine linked without copying")
                stage = "guided completion"
                page.goto(routine_url)
                page.get_by_role(
                    "button", name="Start or resume guided routine"
                ).click()
                page.wait_for_url(re.compile(r".*/routines/sessions/.*"))
                session_url = page.url.split("?")[0]
                page.goto(session_url + "?mode=overview")
                for index in range(1, 5):
                    page.get_by_role(
                        "button", name=f"Complete step {index}", exact=True
                    ).click()
                expect(page.locator("main")).to_contain_text("All 4 steps are complete")
                page.goto(plan_url)
                expect(page.locator("main")).to_contain_text(
                    "1 linked guided runs completed today"
                )
                checks.append("Guided completion updates care-plan real data")
                stage = "observation"
                page.goto(origin + "/observations")
                page.get_by_role("link", name="Add observation", exact=True).click()
                page.locator("#observation-activity").fill(
                    "Fictional chosen observation"
                )
                page.locator("#observation-time").fill(
                    datetime.now(
                        __import__("zoneinfo").ZoneInfo(app.config["APP_TIMEZONE"])
                    ).strftime("%H:%M:%S")
                )
                page.locator("#observation-notes").fill(
                    "A familiar choice was offered."
                )
                page.locator("#observation-save-button").click()
                with app.app_context():
                    oid = db.session.scalar(
                        select(Observation.id).where(
                            Observation.activity == "Fictional chosen observation"
                        )
                    )
                assert oid is not None
                page.goto(plan_url)
                expect(page.locator("main")).to_contain_text(
                    "Fictional chosen observation"
                )
                stage = "handoff generation and review"
                page.goto(origin + "/care/handoffs/studio")
                page.locator("#shift-recipient").select_option(helper)
                # Include the just-recorded observation; end boundaries are exclusive.
                now = datetime.now().astimezone(
                    __import__("zoneinfo").ZoneInfo(app.config["APP_TIMEZONE"])
                )
                page.locator("#shift-start").fill(
                    (now - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M")
                )
                page.locator("#shift-end").fill(
                    (now + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M")
                )
                page.locator("details").filter(
                    has=page.get_by_text(
                        "Choose suggested sections & observations", exact=True
                    )
                ).locator("summary").click()
                page.locator("input[name=categories][value=observations]").check()
                page.locator(f'input[name=observation_ids][value="{oid}"]').check()
                page.get_by_role(
                    "button", name="Generate suggestion", exact=True
                ).click()
                expect(page.locator("#draft-summary")).to_have_value(
                    re.compile(".*Fictional chosen observation.*", re.S)
                )
                text = page.locator("#draft-summary").input_value()
                assert "Fictional picture rhythm" in text
                page.locator("#draft-summary").fill(
                    text + "\n\nAdditional note: picture choices are ready."
                )
                page.locator("#draft-state").select_option("ready")
                page.get_by_role("button", name="Save private draft").click()
                page.wait_for_url(re.compile(r".*/drafts/[a-f0-9]{32}$"))
                draft_url = page.url
                page.locator("input[name=confirm]").check()
                page.get_by_role(
                    "button", name="Share reviewed handoff", exact=True
                ).click()
                page.wait_for_url(re.compile(r".*/care/handoffs/[a-f0-9]{32}$"))
                handoff_url = page.url
                helper_ctx = browser.new_context()
                helper_page = helper_ctx.new_page()
                login(helper_page, "commercial-helper@example.com")
                select_profile(helper_page)
                assert helper_page.goto(draft_url).status == 404
                helper_page.goto(handoff_url)
                expect(helper_page.locator("main")).to_contain_text(
                    "picture choices are ready"
                )
                helper_page.get_by_role(
                    "button", name="Acknowledge handoff", exact=True
                ).click()
                expect(helper_page.locator("main")).to_contain_text("Acknowledged")
                checks.append(
                    "Selected observation, deterministic shift draft, edited review, explicit sharing and recipient acknowledgment"
                )
                foreign_ctx = browser.new_context()
                foreign = foreign_ctx.new_page()
                login(foreign, "commercial-outsider@example.com")
                for url in [plan_url, draft_url, handoff_url, routine_url + "/print"]:
                    assert foreign.goto(url).status == 404
                checks.append(
                    "Unrelated workspace cannot access plan, draft, handoff or print"
                )
                stage = "responsive and print"
                pages = [
                    plan_url,
                    plan_url + "/edit",
                    origin + "/care/handoffs/studio",
                    routine_url + "/builder",
                    routine_url + "/print",
                ]
                for width in [1440, 1280, 1024, 768, 390, 320]:
                    page.set_viewport_size(dict(width=width, height=1000))
                    for url in pages:
                        response = page.goto(url)
                        assert response.status == 200
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth+1"
                        ), f"Overflow at {width}: {url}"
                    page.goto(plan_url)
                    page.screenshot(
                        path=str(out / f"care-plan-{width}.png"), full_page=True
                    )
                page.goto(routine_url + "/print")
                page.emulate_media(media="print")
                expect(page.locator(".site-header")).not_to_be_visible()
                expect(page.locator(".print-controls")).not_to_be_visible()
                expect(page.locator(".printable-routine")).to_be_visible()
                page.pdf(
                    path=str(out / "fictional-routine.pdf"),
                    format="A4",
                    print_background=True,
                )
                checks.append(
                    "30 viewport/page checks at six requested widths; authorized print PDF rendered"
                )
                assert not errors, errors
                browser.close()
        except Exception:
            (out / "result.json").write_text(
                json.dumps(
                    dict(status="failed", stage=stage, checks=checks, errors=errors),
                    indent=2,
                )
            )
            raise
        finally:
            server.shutdown()
            thread.join(timeout=10)
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
    result = dict(status="passed", checks=checks, js_errors=errors)
    (out / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
