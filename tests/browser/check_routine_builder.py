"""Fictional end-to-end builder, keyboard/pointer/touch and native form verification."""

import json, logging, sys, tempfile, threading, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from flask_migrate import upgrade
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from sqlalchemy import select
from olumira import create_app
from olumira.extensions import db
from olumira.models import WorkspaceMembership, CareProfile, Routine
from support import create_user, PASSWORD


def main():
    artifacts = ROOT / "artifacts" / "day22"
    artifacts.mkdir(parents=True, exist_ok=True)
    checks = []
    failures = []
    stage = "startup"
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
        owner_id, workspace_id = create_user(app, "fiction-builder-browser@example.com")
        helper_id, _ = create_user(app, "fiction-builder-helper@example.com")
        with app.app_context():
            db.session.add(
                WorkspaceMembership(
                    id="a" * 32,
                    workspace_id=workspace_id,
                    user_id=helper_id,
                    role="caregiver",
                    status="active",
                )
            )
            db.session.add(
                CareProfile(
                    id="b" * 32,
                    workspace_id=workspace_id,
                    display_name="Fictional Fern",
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
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                page.on(
                    "pageerror",
                    lambda error: failures.append("JavaScript runtime error"),
                )

                def login(page, email):
                    page.goto(origin + "/auth/login")
                    page.locator("#email").fill(email)
                    page.locator("#password").fill(PASSWORD)
                    page.locator(".auth-submit").click()
                    page.wait_for_url(origin + "/")

                login(page, "fiction-builder-browser@example.com")
                stage = "template and live preview"
                page.goto(origin + "/routines")
                page.get_by_role("link", name="Create routine", exact=False).click()
                page.locator("#builder-name").fill("Fictional garden morning")
                page.locator("#builder-description").fill(
                    "A calm fictional sequence to explore together."
                )
                page.locator("#builder-color").select_option("lavender")
                page.locator("[name=step_title]").first.fill("Choose clothes")
                page.locator("#add-routine-step").click()
                page.locator("[name=step_title]").nth(1).fill("Share breakfast")
                page.locator("#add-routine-step").click()
                page.locator("[name=step_title]").nth(2).fill("Read a story")
                assert (
                    page.locator("#preview-name").inner_text()
                    == "Fictional garden morning"
                )
                assert (
                    page.locator("#routine-live-preview")
                    .get_attribute("class")
                    .endswith("tone-lavender")
                )
                assert page.locator("#preview-steps li").count() == 3
                stage = "keyboard reorder and removal focus"
                last = page.locator("[data-step-editor]").nth(2)
                last.locator("[data-step-up]").focus()
                page.keyboard.press("Enter")
                assert (
                    page.locator("[name=step_title]").nth(1).input_value()
                    == "Read a story"
                )
                assert (
                    page.locator("[data-step-editor]")
                    .nth(1)
                    .locator("[data-step-up]")
                    .evaluate("(el)=>el===document.activeElement")
                )
                page.locator("#add-routine-step").click()
                page.locator("[name=step_title]").nth(3).fill(
                    "Remove this fictional step"
                )
                page.locator("[data-step-editor]").nth(3).locator(
                    "[data-step-remove]"
                ).click()
                assert (
                    page.locator("[name=step_title]")
                    .nth(2)
                    .evaluate("(el)=>el===document.activeElement")
                )
                stage = "pointer drag and save"
                handle = (
                    page.locator("[data-step-editor]")
                    .nth(2)
                    .locator(".step-drag-handle")
                )
                handle.scroll_into_view_if_needed()
                box = handle.bounding_box()
                target = page.locator("[data-step-editor]").nth(1)
                target.scroll_into_view_if_needed()
                # Pointer capture continues across scroll. Re-read both viewport positions.
                box = handle.bounding_box()
                target_box = target.bounding_box()
                page.mouse.move(
                    box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                )
                page.mouse.down()
                page.mouse.move(target_box["x"] + 20, target_box["y"] + 30, steps=10)
                page.mouse.up()
                assert (
                    page.locator("[name=step_title]").nth(1).input_value()
                    == "Share breakfast"
                )
                page.locator("#save-routine").click()
                page.wait_for_url("**/routines/*")
                sequence_url = page.url
                assert page.locator(
                    ".routine-sequence-list h3"
                ).all_text_contents() == [
                    "Choose clothes",
                    "Share breakfast",
                    "Read a story",
                ]
                checks += [
                    "live preview and color",
                    "keyboard reorder and focus",
                    "add/remove focus",
                    "pointer drag order saved",
                ]
                stage = "persistence editing and conflict"
                page.get_by_role("link", name="Edit routine", exact=True).click()
                edit_url = page.url
                assert (
                    page.locator("[name=step_title]").nth(1).input_value()
                    == "Share breakfast"
                )
                stale = page.context.new_page()
                stale.goto(edit_url)
                page.locator("#builder-description").fill(
                    "Updated fictional description"
                )
                page.locator("#save-routine").click()
                page.wait_for_url(sequence_url)
                stale.locator("#builder-name").fill("Fictional unsaved second editor")
                stale.locator("#save-routine").click()
                stale.locator("#builder-error").wait_for()
                assert (
                    stale.locator("#builder-name").input_value()
                    == "Fictional unsaved second editor"
                )
                stale.close(run_before_unload=False)
                checks.append(
                    "saved order survives reload; stale editor gets conflict with draft retained"
                )
                stage = "duplicate archive restore search"
                page.goto(origin + "/routines")
                card = page.locator(".routine-library-card").filter(
                    has=page.get_by_role(
                        "heading", name="Fictional garden morning", exact=True
                    )
                )
                card.locator("summary").click()
                card.get_by_role("button", name="Duplicate", exact=True).click()
                page.wait_for_url("**/builder")
                assert page.locator("#builder-name").input_value().endswith("(copy)")
                page.locator("#save-routine").click()
                page.wait_for_url("**/routines/*")
                page.goto(origin + "/routines")
                page.locator("#routine-search").fill("Fictional garden morning (copy)")
                page.get_by_role("button", name="Apply filters").click()
                assert page.locator(".routine-library-card").count() == 1
                page.locator(".routine-card-options summary").click()
                page.once("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Archive", exact=True).click()
                page.wait_for_url("**/routines?status=active")
                page.locator("#library-status").select_option("archived")
                page.get_by_role("button", name="Apply filters").click()
                assert page.get_by_role(
                    "heading", name="Fictional garden morning (copy)", exact=True
                ).is_visible()
                page.locator(".routine-card-options summary").click()
                page.get_by_role("button", name="Restore", exact=True).click()
                checks.append("duplicate, search, archive and restore persist")
                stage = "unsaved changes warning"
                page.goto(edit_url)
                page.locator("#builder-name").fill("Fictional unsaved navigation")
                page.once("dialog", lambda dialog: dialog.dismiss())
                page.get_by_role(
                    "link", name="Routine library", exact=False
                ).first.click()
                assert page.url == edit_url
                page.once("dialog", lambda dialog: dialog.accept())
                page.goto(origin + "/routines")
                checks.append("unsaved navigation can be cancelled")
                stage = "responsive layouts labels and contrast"
                routes = [
                    ("/routines", "library"),
                    ("/routines/new?template=morning", "builder"),
                    (sequence_url.removeprefix(origin), "sequence"),
                ]
                for width in [1440, 1280, 1024, 768, 390, 320]:
                    page.set_viewport_size({"width": width, "height": 1000})
                    for path, name in routes:
                        assert page.goto(origin + path).status == 200
                        assert page.locator("h1").count() == 1
                        assert (
                            page.get_by_role("navigation", name="Main navigation")
                            .locator("a[aria-current=page]")
                            .count()
                            == 1
                        )
                        for navigation in page.get_by_role("navigation").all():
                            assert (
                                navigation.locator("a[aria-current=page]").count() <= 1
                            )
                        assert not page.evaluate(
                            "document.documentElement.scrollWidth > innerWidth"
                        ), f"Overflow {name} {width}"
                        for field in page.locator(
                            "input:not([type=hidden]),select,textarea"
                        ).all():
                            if field.is_visible():
                                field_id = field.get_attribute("id")
                                assert (
                                    field_id
                                    and page.locator(
                                        'label[for="' + field_id + '"]'
                                    ).count()
                                ), f"Unlabeled field {name}"
                        if width == 1440:
                            low = page.evaluate(r"""() => {
                                const rgb=v=>(v.match(/[\d.]+/g)||[]).map(Number),blend=(t,b)=>t.slice(0,3).map((v,i)=>v*(t[3]??1)+b[i]*(1-(t[3]??1)));
                                const bg=e=>!e?[255,255,255]:blend(rgb(getComputedStyle(e).backgroundColor),bg(e.parentElement));
                                const lum=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
                                return [...document.querySelectorAll('h1,h2,h3,p,label,summary,button,.text-link')].filter(e=>e.getClientRects().length&&!e.disabled).flatMap(e=>{const s=getComputedStyle(e),b=bg(e),f=lum(blend(rgb(s.color),b)),l=lum(b),r=(Math.max(f,l)+.05)/(Math.min(f,l)+.05),large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700);return r+.01<(large?3:4.5)?[e.tagName+'.'+e.className]:[];});
                            }""")
                            assert not low, "Contrast: " + ",".join(low)
                        page.screenshot(
                            path=str(artifacts / f"{name}-{width}.png"), full_page=True
                        )
                        checks.append(f"{name} at {width}px")
                stage = "mobile touch reorder"
                touch = browser.new_context(
                    is_mobile=True,
                    has_touch=True,
                    viewport={"width": 390, "height": 844},
                )
                touch.add_cookies(page.context.cookies())
                mobile = touch.new_page()
                mobile.on(
                    "pageerror",
                    lambda error: failures.append("Mobile JavaScript runtime error"),
                )
                mobile.goto(edit_url)
                mobile.locator("[data-step-editor]").nth(2).locator(
                    "[data-step-up]"
                ).tap()
                assert (
                    mobile.locator("[name=step_title]").nth(1).input_value()
                    == "Read a story"
                )
                # A touch pointer on the drag handle follows the same pointer-capture path.
                row = mobile.locator("[data-step-editor]").nth(2)
                handle = row.locator(".step-drag-handle")
                handle.scroll_into_view_if_needed()
                target = mobile.locator("[data-step-editor]").nth(1)
                target.scroll_into_view_if_needed()
                box = handle.bounding_box()
                target_box = target.bounding_box()
                cdp = touch.new_cdp_session(mobile)
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {
                        "type": "touchStart",
                        "touchPoints": [
                            {
                                "x": box["x"] + box["width"] / 2,
                                "y": box["y"] + box["height"] / 2,
                            }
                        ],
                    },
                )
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {
                        "type": "touchMove",
                        "touchPoints": [
                            {"x": target_box["x"] + 20, "y": target_box["y"] + 30}
                        ],
                    },
                )
                cdp.send(
                    "Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}
                )
                assert (
                    mobile.locator("[name=step_title]").nth(1).input_value()
                    == "Share breakfast"
                )
                mobile.locator("#save-routine").click()
                mobile.wait_for_url(sequence_url)
                touch.close()
                checks.append("mobile touch move controls and pointer drag path")
                stage = "native no-JavaScript draft controls"
                nojs = browser.new_context(
                    java_script_enabled=False, viewport={"width": 390, "height": 900}
                )
                nojs.add_cookies(page.context.cookies())
                native = nojs.new_page()
                native.goto(origin + "/routines/new")
                native.locator("#builder-name").fill("Fictional native form")
                native.locator("[name=step_title]").first.fill("Native first step")
                native.locator("#add-routine-step").click()
                assert native.locator("[data-step-editor]").count() == 2
                native.locator("[name=step_title]").nth(1).fill("Native second step")
                native.locator("[data-step-editor]").nth(1).locator(
                    "[data-step-up]"
                ).click()
                assert (
                    native.locator("[name=step_title]").first.input_value()
                    == "Native second step"
                )
                native.locator("#save-routine").click()
                native.wait_for_url("**/routines/*")
                assert (
                    native.locator(".routine-sequence-list h3").first.inner_text()
                    == "Native second step"
                )
                nojs.close()
                checks.append("no-JavaScript add, reorder and save")
                page.emulate_media(reduced_motion="reduce")
                page.goto(edit_url)
                assert page.evaluate(
                    'matchMedia("(prefers-reduced-motion: reduce)").matches'
                )
                checks.append("reduced motion respected")
                browser.close()
        except Exception as error:
            print(
                type(error).__name__,
                [
                    (Path(f.filename).name, f.lineno)
                    for f in traceback.extract_tb(error.__traceback__)
                    if "check_routine_builder" in f.filename
                ],
            )
            print(str(error)[:1000])
            failures.append("Browser validation failed during " + stage)
        finally:
            server.shutdown()
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
    result = {"checks": checks, "failures": failures, "fictional_data_only": True}
    (artifacts / "report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
