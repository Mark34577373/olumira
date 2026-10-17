"""Repeatable fictional family demo, responsive checks and real permission changes."""

import json
import logging
import re
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from flask_migrate import upgrade
from sqlalchemy import select
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from olumira import create_app
from olumira.extensions import db
from olumira.models import EmailOutbox, WorkspaceMembership, User
from services.email_delivery import cipher
from test_account_recovery import email_link


def main():
    artifacts = ROOT / "artifacts" / "days17-21"
    artifacts.mkdir(parents=True, exist_ok=True)
    checks = []
    failures = []
    stage = "startup"
    with tempfile.TemporaryDirectory() as directory:
        app = create_app(
            {
                "APP_ENV": "testing",
                "DATABASE": str(Path(directory) / "demo.db"),
                "AUTH_LOGIN_IP_LIMIT": "1000 per hour",
                "AUTH_LOGIN_ACCOUNT_LIMIT": "1000 per hour",
                "AUTH_REGISTER_LIMIT": "1000 per hour",
            }
        )
        with app.app_context():
            upgrade()
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        app.config["PUBLIC_APP_URL"] = origin
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                owner = browser.new_page(viewport={"width": 1440, "height": 1000})
                helper = browser.new_page(viewport={"width": 1440, "height": 1000})
                viewer = browser.new_page(viewport={"width": 1440, "height": 1000})
                for page in [owner, helper, viewer]:
                    page.on(
                        "pageerror",
                        lambda error: failures.append("JavaScript runtime error"),
                    )

                def register(page, email, name):
                    page.goto(origin + "/auth/register")
                    page.locator("#display_name").fill(name)
                    page.locator("#email").fill(email)
                    page.locator("#password").fill(
                        "Fictional fern garden passphrase 42"
                    )
                    page.locator("#confirm_password").fill(
                        "Fictional fern garden passphrase 42"
                    )
                    page.locator(".auth-submit").click()
                    page.wait_for_url("**/auth/check-email")
                    _, link, _ = email_link(app, "verify_email")
                    page.goto(link)
                    page.locator(".auth-submit").click()
                    page.get_by_role(
                        "heading", name="Email verified", exact=True
                    ).wait_for()
                    page.goto(origin + "/auth/login")
                    page.locator("#email").fill(email)
                    page.locator("#password").fill(
                        "Fictional fern garden passphrase 42"
                    )
                    page.locator(".auth-submit").click()
                    page.wait_for_url(origin + "/")

                def invitation_link(email):
                    with app.app_context():
                        jobs = list(
                            db.session.scalars(
                                select(EmailOutbox).where(
                                    EmailOutbox.kind == "invitation",
                                    EmailOutbox.cancelled_at.is_(None),
                                )
                            )
                        )
                        for job in jobs:
                            payload = json.loads(
                                cipher().decrypt(job.encrypted_payload.encode())
                            )
                            if payload["recipient"] == email:
                                return re.search(
                                    r"https?://\S+#token=[A-Za-z0-9_-]{43}",
                                    payload["text"],
                                ).group(0)
                    raise AssertionError("Expected fictional invitation")

                def invite(email, role):
                    owner.goto(origin + "/workspaces/settings")
                    owner.locator("#invite-email").fill(email)
                    owner.locator("#invite-role").select_option(role)
                    owner.get_by_role(
                        "button", name="Send invitation", exact=True
                    ).click()
                    owner.get_by_role("status").wait_for()
                    return invitation_link(email)

                stage = "owner registration verification and workspace creation"
                register(owner, "fiction-owner@example.com", "Fictional Rowan")
                owner.goto(origin + "/workspaces")
                owner.locator("#workspace-name").fill("Fictional Cedar Family")
                owner.get_by_role("button", name="Create workspace", exact=True).click()
                owner.get_by_role(
                    "heading", name="Fictional Cedar Family", exact=True
                ).wait_for()
                workspace_id = owner.locator("#active-workspace").input_value()
                stage = "profile creation and personalization"
                owner.get_by_role("link", name="Add care profile", exact=True).click()
                owner.locator("#display_name").fill("Fictional Fern")
                owner.locator("#communication").fill(
                    "Offer two short choices and allow time to respond."
                )
                owner.locator("#routine_preferences").fill(
                    "A calm start with a visual checklist."
                )
                owner.locator("#interests").fill(
                    "Gardens and imaginary woodland stories."
                )
                owner.get_by_role(
                    "button", name="Save care profile", exact=True
                ).click()
                profile_url = owner.url
                profile_id = profile_url.rsplit("/", 1)[1]
                owner.get_by_role(
                    "button", name="Use this care profile", exact=True
                ).click()
                stage = "profile routines observations and communication"
                owner.goto(origin + "/routines")
                owner.locator("#routine-name").fill("Fictional garden walk")
                owner.get_by_role("button", name="Add routine", exact=True).click()
                owner.goto(origin + "/observations")
                owner.locator("#observation-activity").fill("Fictional calm morning")
                owner.locator("#observation-notes").fill(
                    "Fictional demonstration only: enjoyed choosing a story."
                )
                owner.get_by_role("button", name="Save observation", exact=True).click()
                owner.goto(origin + "/communication")
                assert owner.get_by_text(
                    "Offer two short choices and allow time to respond.", exact=False
                ).is_visible()
                checks.append(
                    "verified registration -> private workspace -> personalized profile -> scoped care content"
                )
                stage = "new-account caregiver invitation acceptance"
                link = invite("fiction-helper@example.com", "caregiver")
                helper.goto(link)
                assert "#" not in helper.url
                assert (
                    helper.locator("main")
                    .get_by_role("link", name="Create account", exact=True)
                    .is_visible()
                )
                register(helper, "fiction-helper@example.com", "Fictional Sage")
                helper.goto(link)
                assert "#" not in helper.url
                helper.get_by_role(
                    "button", name="Accept invitation", exact=True
                ).click()
                helper.wait_for_url(origin + "/")
                helper.locator("#active-profile").select_option(profile_id)
                helper.get_by_role("button", name="Switch profile", exact=True).click()
                assert helper.get_by_role(
                    "heading", name="Fictional calm morning", exact=True
                ).is_visible()
                helper.goto(origin + "/routines")
                helper.locator("#routine-name").fill("Fictional shared reading")
                helper.get_by_role("button", name="Add routine", exact=True).click()
                owner.goto(origin + "/routines")
                assert owner.get_by_role(
                    "link", name="Fictional shared reading", exact=True
                ).is_visible()
                checks.append(
                    "new account accepts invitation and collaborates on shared profile routines"
                )
                stage = "viewer read-only and unrelated family isolation"
                register(viewer, "fiction-viewer@example.com", "Fictional Willow")
                assert not viewer.get_by_text(
                    "Fictional garden walk", exact=True
                ).count()
                assert viewer.goto(profile_url).status == 404
                link = invite("fiction-viewer@example.com", "viewer")
                viewer.goto(link)
                viewer.get_by_role(
                    "button", name="Accept invitation", exact=True
                ).click()
                viewer.wait_for_url(origin + "/")
                viewer.locator("#active-profile").select_option(profile_id)
                viewer.get_by_role("button", name="Switch profile", exact=True).click()
                viewer.goto(origin + "/routines")
                assert viewer.locator("#routine-name").count() == 0
                assert viewer.get_by_text(
                    "Fictional garden walk", exact=True
                ).is_visible()
                assert viewer.locator(".routine-item").first.is_disabled()
                checks.append(
                    "unrelated family denied; invited viewer reads content without edit controls"
                )
                stage = "responsive workspace and profile pages"
                routes = [
                    ("/workspaces", "workspaces"),
                    ("/workspaces/settings", "settings"),
                    ("/workspaces/profiles/new", "new-profile"),
                    ("/workspaces/profiles/" + profile_id, "profile"),
                    ("/workspaces/profiles/" + profile_id + "/edit", "edit-profile"),
                    ("/workspaces/accept", "accept"),
                    ("/", "dashboard"),
                ]
                for width in [1440, 1280, 1024, 768, 390, 320]:
                    owner.set_viewport_size({"width": width, "height": 1000})
                    for path, name in routes:
                        assert owner.goto(origin + path).status == 200
                        assert owner.locator("h1").count() == 1
                        assert not owner.evaluate(
                            "document.documentElement.scrollWidth > innerWidth"
                        ), f"Overflow {name} at {width}"
                        for control in owner.locator(
                            "input:not([type=hidden]),select,textarea"
                        ).all():
                            if control.is_visible():
                                control_id = control.get_attribute("id")
                                assert (
                                    control_id
                                    and owner.locator(
                                        'label[for="' + control_id + '"]'
                                    ).count()
                                ), f"Missing label on {name}"
                        if width == 1440:
                            contrast_failures = owner.evaluate(r"""() => {
                                const rgb = value => (value.match(/[\d.]+/g) || []).map(Number);
                                const blend = (top,bottom) => top.slice(0,3).map((v,i)=>v*(top[3] ?? 1)+bottom[i]*(1-(top[3] ?? 1)));
                                const background = el => !el ? [255,255,255] : blend(rgb(getComputedStyle(el).backgroundColor),background(el.parentElement));
                                const luminance = c => c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
                                return [...document.querySelectorAll('h1,h2,h3,p,label,summary,.workspace-card a,.workspace-context a,.role-badge,button')]
                                  .filter(el=>el.getClientRects().length && !el.disabled && getComputedStyle(el).visibility!=='hidden')
                                  .flatMap(el=>{
                                    const style=getComputedStyle(el),bg=background(el);
                                    const foreground=luminance(blend(rgb(style.color),bg)),back=luminance(bg);
                                    const ratio=(Math.max(foreground,back)+.05)/(Math.min(foreground,back)+.05);
                                    const large=parseFloat(style.fontSize)>=24 || (parseFloat(style.fontSize)>=18.66 && parseInt(style.fontWeight)>=700);
                                    return ratio+.01<(large?3:4.5)?[el.tagName+'.'+el.className]:[];
                                  });
                            }""")
                            assert not contrast_failures, "Text contrast: " + ",".join(
                                contrast_failures
                            )
                        owner.screenshot(
                            path=str(artifacts / f"{name}-{width}.png"), full_page=True
                        )
                        checks.append(f"{name} at {width}px")
                stage = "keyboard context switching and focus"
                owner.goto(origin + "/")
                owner.keyboard.press("Tab")
                assert owner.locator(".skip-link").evaluate(
                    "(el)=>el===document.activeElement"
                )
                owner.keyboard.press("Enter")
                assert owner.locator("main").evaluate(
                    "(el)=>el===document.activeElement"
                )
                owner.locator("#active-profile").focus()
                assert owner.locator("#active-profile").evaluate(
                    '(el)=>getComputedStyle(el).outlineStyle!=="none"'
                )
                checks.append("keyboard skip link and visible selection focus")
                stage = "live role change and removal"
                with app.app_context():
                    helper_id = db.session.scalar(
                        select(User.id).where(
                            User.email == "fiction-helper@example.com"
                        )
                    )
                    member_id = db.session.scalar(
                        select(WorkspaceMembership.id).where(
                            WorkspaceMembership.workspace_id == workspace_id,
                            WorkspaceMembership.user_id == helper_id,
                        )
                    )
                owner.goto(origin + "/workspaces/settings")
                owner.locator("#role-" + member_id).select_option("viewer")
                owner.locator("#role-" + member_id).locator("..").get_by_role(
                    "button", name="Update role", exact=True
                ).click()
                helper.goto(origin + "/routines")
                assert helper.locator("#routine-name").count() == 0
                owner.on("dialog", lambda dialog: dialog.accept())
                owner.locator(
                    'form[action="/workspaces/members/' + member_id + '/remove"]'
                ).get_by_role("button").click()
                owner.get_by_role("status").wait_for()
                helper.goto(origin + "/")
                assert (
                    helper.locator(
                        '#active-workspace option[value="' + workspace_id + '"]'
                    ).count()
                    == 0
                )
                checks.append(
                    "role demotion and membership removal apply during active browser sessions"
                )
                browser.close()
        except Exception as error:
            import traceback

            print(
                type(error).__name__,
                [
                    (Path(frame.filename).name, frame.lineno)
                    for frame in traceback.extract_tb(error.__traceback__)
                    if "check_workspaces" in frame.filename
                ],
            )
            print(re.sub(r"[A-Za-z0-9_-]{43}", "[redacted]", str(error))[:1200])
            failures.append("Browser validation failed during " + stage)
        finally:
            server.shutdown()
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
    report = {"checks": checks, "failures": failures, "fictional_data_only": True}
    (artifacts / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
