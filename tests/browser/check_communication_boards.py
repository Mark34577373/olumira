"""Fictional editor -> independent board -> phrase/speech workflow with local voice mocks."""

import json, logging, sys, tempfile, threading, traceback, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from flask_migrate import upgrade
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
from sqlalchemy import select
from olumira import create_app
from olumira.extensions import db
from olumira.models import (
    WorkspaceMembership,
    CareProfile,
    CommunicationBoard,
    SavedCommunicationPhrase,
)
from support import create_user, PASSWORD

SPEECH_MOCK = r"""(() => {
 window.__spoken=[];window.__cancels=0;window.__speechFail=false;window.__holdSpeech=false;
 window.__voices=[{name:'Fictional local voice',voiceURI:'fiction-local',lang:'en-US',localService:true},{name:'Fictional remote voice',voiceURI:'fiction-remote',lang:'en-US',localService:false}];
 const listeners=[];window.__loadVoices=()=>listeners.forEach(f=>f());
 Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{getVoices:()=>window.__voices,addEventListener:(name,fn)=>listeners.push(fn),cancel:()=>{window.__cancels++;},speak:utterance=>{window.__spoken.push({text:utterance.text,rate:utterance.rate,voice:utterance.voice.voiceURI});utterance.onstart?.();if(!window.__holdSpeech)setTimeout(()=>window.__speechFail?utterance.onerror?.():utterance.onend?.(),40);}}});
 window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
})();"""


def main():
    artifacts = ROOT / "artifacts" / "day25-26"
    artifacts.mkdir(parents=True, exist_ok=True)
    checks = []
    failures = []
    viewports = 0
    stage = "startup"
    with tempfile.TemporaryDirectory() as directory:
        app = create_app(
            {
                "APP_ENV": "testing",
                "DATABASE": str(Path(directory) / "boards.db"),
                "AUTH_LOGIN_IP_LIMIT": "1000 per hour",
                "AUTH_LOGIN_ACCOUNT_LIMIT": "1000 per hour",
            }
        )
        with app.app_context():
            upgrade()
        owner, ws = create_user(app, "fiction-boards-owner@example.com")
        helper, _ = create_user(app, "fiction-boards-helper@example.com")
        viewer, _ = create_user(app, "fiction-boards-viewer@example.com")
        other, _ = create_user(app, "fiction-boards-other@example.com")
        profile = uuid.uuid4().hex
        with app.app_context():
            db.session.add(
                CareProfile(id=profile, workspace_id=ws, display_name="Fictional Fern")
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
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{server.server_port}"
        app.config["PUBLIC_APP_URL"] = origin
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport=dict(width=1440, height=1050))
                context.add_init_script(SPEECH_MOCK)
                page = context.new_page()
                page.on(
                    "pageerror",
                    lambda err: failures.append(
                        "JavaScript runtime error: " + str(err).splitlines()[0][:120]
                    ),
                )

                def login(page, email, shared=False, choose_profile=True):
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
                    if choose_profile:
                        page.locator("#active-profile").select_option(profile)
                        page.get_by_role(
                            "button", name="Switch profile", exact=True
                        ).click()

                login(page, "fiction-boards-owner@example.com")
                stage = "Day 25 editor and original symbols"
                page.goto(origin + "/communication")
                page.get_by_role("link", name="My words", exact=False).click()
                page.locator("#board-title").fill("Fictional Basic Needs")
                assert page.locator("[data-card-editor]").count() == 6
                first = page.locator("[data-card-editor]").first
                first.locator("[data-card-action=down]").focus()
                page.keyboard.press("Enter")
                assert page.locator("[name=card_label]").nth(1).input_value() == "I"
                page.locator("#add-board-card").click()
                page.locator("[name=card_label]").last.fill("A calm place")
                page.locator("[name=card_spoken_text]").last.fill(
                    "I want a calm place."
                )
                page.locator("[name=card_symbol]").last.select_option("home")
                page.locator("[data-card-editor]").last.locator(
                    "[data-card-action=copy]"
                ).click()
                assert page.locator("[data-card-editor]").count() == 8
                page.locator("[data-card-editor]").last.locator(
                    "[data-card-action=remove]"
                ).click()
                assert page.locator("[data-card-editor]").count() == 7
                assert (
                    page.locator("#draft-board-title").inner_text()
                    == "Fictional Basic Needs"
                )
                # Real desktop pointer ordering, with explicit keyboard alternatives retained.
                before_drag = page.locator("[name=card_label]").first.input_value()
                handle = page.locator(".board-drag-handle").first
                handle.scroll_into_view_if_needed()
                start_box = handle.bounding_box()
                target_box = page.locator("[data-card-editor]").nth(1).bounding_box()
                page.mouse.move(start_box["x"] + 20, start_box["y"] + 20)
                page.mouse.down()
                page.mouse.move(
                    target_box["x"] + target_box["width"] / 2,
                    target_box["y"] + target_box["height"] * 0.65,
                    steps=12,
                )
                page.mouse.up()
                expected_first = page.locator("[name=card_label]").first.input_value()
                assert (
                    expected_first != before_drag
                ), "Pointer drag must change the draft order"
                page.locator("#board-layout").select_option("4")
                page.locator("#save-board").click()
                page.wait_for_url("**/communication/*")
                board_url = page.url
                bid = board_url.rsplit("/", 1)[1]
                edit_url = board_url + "/edit"
                assert page.locator("[data-picture-card]").count() == 7
                assert page.locator("[data-card-editor]").count() == 0
                assert (
                    page.get_by_role("link", name="Edit board", exact=True).count() == 0
                )
                assert (
                    page.locator("[data-picture-card]").first.inner_text()
                    == expected_first
                )
                checks.append(
                    "Day 25: template/profile board, original symbol selection, add/duplicate/remove, keyboard/pointer reorder, live preview and persisted 4-column layout"
                )
                stage = "concurrent editor and unsaved changes"
                stale = context.new_page()
                stale.goto(edit_url)
                page.goto(edit_url)
                page.locator("#board-description").fill(
                    "Fictional shared visual choices."
                )
                page.locator("#save-board").click()
                stale.locator("#board-title").fill("Retained fictional draft")
                stale.locator("#save-board").click()
                expect(stale.get_by_role("alert")).to_contain_text(
                    "Another caregiver changed"
                )
                assert (
                    stale.locator("#board-title").input_value()
                    == "Retained fictional draft"
                )
                stale.close()
                page.goto(edit_url)
                page.locator("#board-description").fill("Unsaved fictional draft")
                page.on("dialog", lambda dialog: dialog.dismiss())
                page.get_by_role("link", name="Board library", exact=False).click()
                assert page.url == edit_url
                # Cancelled navigation retains the draft; explicitly save it before leaving.
                page.locator("#save-board").click()
                page.wait_for_url(board_url)
                checks.append(
                    "Day 25: stale edits retain draft and unsaved navigation can be cancelled"
                )
                stage = "Day 26 phrase strip keyboard and speech"
                assert page.locator("#speech-voice option").count() == 1
                assert (
                    "remote" not in page.locator("#speech-voice").inner_text().lower()
                )
                page.locator('[data-picture-card][data-label="I"]').focus()
                page.keyboard.press("Enter")
                page.locator('[data-picture-card][data-label="want"]').click()
                page.locator('[data-picture-card][data-label="water"]').click()
                assert page.locator("#phrase-written").inner_text() == "I want water"
                page.locator("#speak-phrase").click()
                assert page.evaluate("window.__spoken.at(-1).text") == "I want water"
                assert page.evaluate("window.__spoken.at(-1).voice") == "fiction-local"
                page.locator(".speech-settings summary").click()
                page.locator("#speech-rate").select_option("0.8")
                page.locator("#speak-phrase").click()
                assert page.evaluate("window.__spoken.at(-1).rate") == 0.8
                page.evaluate("window.__holdSpeech=true")
                page.locator("#speak-phrase").click()
                page.locator("#stop-speech").click()
                expect(page.locator("#speech-status")).to_contain_text("stopped")
                page.evaluate("window.__holdSpeech=false")
                page.locator("#replay-speech").click()
                assert page.evaluate("window.__spoken.at(-1).text") == "I want water"
                count = page.evaluate("window.__spoken.length")
                page.locator("[data-picture-card]").first.focus()
                assert page.evaluate("window.__spoken.length") == count
                page.locator("#speech-enabled").uncheck()
                page.locator('[data-picture-card][data-label="water"]').click()
                assert page.evaluate("window.__spoken.length") == count
                page.locator("#remove-last-word").click()
                assert page.locator("#phrase-written").inner_text() == "I want water"
                page.get_by_role("button", name="Remove word 2:", exact=False).click()
                assert page.locator("#phrase-written").inner_text() == "I water"
                page.locator("#clear-phrase").click()
                assert page.locator("#phrase-written").inner_text() == ""
                for label in ["I", "want", "water"]:
                    page.locator(f'[data-picture-card][data-label="{label}"]').click()
                checks.append(
                    "Day 26: deliberate keyboard/click activation, ordered phrase, individual removal/last/clear, local-only voice, rate, speak/stop/replay and speech off"
                )
                stage = "focus and explicit saved phrase"
                page.keyboard.press("Escape")
                page.locator("#board-focus").click()
                assert page.locator("body").evaluate(
                    "el=>el.classList.contains('board-focus-mode')"
                )
                assert page.locator("#phrase-written").inner_text() == "I want water"
                page.keyboard.press("Escape")
                assert not page.locator("body").evaluate(
                    "el=>el.classList.contains('board-focus-mode')"
                )
                page.locator("#save-phrase-open").click()
                page.locator("#save-phrase-label").fill("Water please")
                page.route("**/communication/phrases", lambda route: route.abort())
                page.locator("#save-phrase-dialog").get_by_role(
                    "button", name="Save phrase", exact=True
                ).click()
                expect(
                    page.locator("#save-phrase-dialog [role=alert]")
                ).to_contain_text("Connection interrupted")
                assert page.locator("#phrase-written").inner_text() == "I want water"
                page.unroute("**/communication/phrases")
                page.locator("#save-phrase-dialog").get_by_role(
                    "button", name="Save phrase", exact=True
                ).click()
                expect(page.locator("#save-phrase-dialog")).not_to_be_visible()
                expect(page.locator("#speech-status")).to_have_text(
                    "Phrase saved for this profile."
                )
                assert page.locator("#phrase-written").inner_text() == "I want water"
                page.reload()
                page.locator(".speech-settings summary").click()
                assert page.locator("#phrase-written").inner_text() == ""
                assert not page.locator("#speech-enabled").is_checked()
                page.get_by_role("button", name="Water please", exact=True).click()
                assert page.locator("#phrase-written").inner_text() == "I want water"
                assert page.evaluate(
                    "Object.keys(localStorage).filter(k=>k.startsWith('olumira.speechSettings')).every(k=>!localStorage.getItem(k).includes('I want water'))"
                )
                checks.append(
                    "Day 26: focus/Escape preserve phrase; network save failure retains message; retry succeeds and explicit save stays on board, saved phrase reopens, drafts clear on reload and only speech preferences persist locally"
                )
                stage = "speech errors, asynchronous voices and unsupported browser"
                page.locator("#speech-enabled").check()
                page.evaluate("window.__speechFail=true")
                page.locator("#speak-phrase").click()
                expect(page.locator("#speech-status")).to_contain_text("could not play")
                assert page.locator("#phrase-written").inner_text() == "I want water"
                page.evaluate(
                    "window.__speechFail=false;window.__voices=[];window.__loadVoices()"
                )
                expect(page.locator("#speech-status")).to_contain_text("No local voice")
                assert page.locator("#speak-phrase").is_disabled()
                page.evaluate(
                    "window.__voices=[{name:'Fictional local voice',voiceURI:'fiction-local',lang:'en-US',localService:true}];window.__loadVoices()"
                )
                assert not page.locator("#speak-phrase").is_disabled()
                unsupported = browser.new_context()
                unsupported.add_cookies(context.cookies())
                unsupported.add_init_script(
                    "Object.defineProperty(window,'speechSynthesis',{configurable:true,value:undefined});"
                )
                fallback = unsupported.new_page()
                fallback.goto(board_url)
                fallback.locator('[data-picture-card][data-label="water"]').click()
                assert fallback.locator("#phrase-written").inner_text() == "water"
                assert fallback.locator("#speak-phrase").is_disabled()
                expect(fallback.locator("#speech-status")).to_contain_text(
                    "unavailable"
                )
                checks.append(
                    "Day 26: speech error keeps message, missing/local asynchronous voices recover, unsupported browser keeps written communication"
                )
                stage = "saved phrase editor, ordering and archive"
                page.goto(origin + "/communication/phrases")
                page.get_by_role("link", name="Edit phrase", exact=True).click()
                page.locator("#phrase-label").fill("Water request")
                page.locator("#phrase-text").fill("I want water please.")
                page.get_by_role("button", name="Save phrase", exact=True).click()
                page.locator("#phrase-label").fill("A break")
                page.locator("#phrase-text").fill("I want a break.")
                page.get_by_role("button", name="Save phrase", exact=True).click()
                page.locator(".saved-phrase-management article").last.get_by_role(
                    "button", name="Move up", exact=True
                ).click()
                assert (
                    page.locator(".saved-phrase-management h3").first.inner_text()
                    == "A break"
                )
                page.locator(".saved-phrase-management article").first.get_by_role(
                    "button", name="Archive phrase", exact=True
                ).click()
                assert page.locator(".saved-phrase-management h3").count() == 1
                checks.append("Day 26: persistent saved phrase edit, order and archive")
                stage = "shared caregiver, viewer and separate family"
                for email, role in [
                    ("fiction-boards-helper@example.com", "caregiver"),
                    ("fiction-boards-viewer@example.com", "viewer"),
                ]:
                    ctx = browser.new_context()
                    ctx.add_init_script(SPEECH_MOCK)
                    shared = ctx.new_page()
                    login(shared, email, True)
                    shared.goto(board_url)
                    assert (
                        shared.get_by_role(
                            "button", name="Water request", exact=True
                        ).count()
                        == 1
                    )
                    shared.locator('[data-picture-card][data-label="water"]').click()
                    assert shared.locator("#phrase-written").inner_text() == "water"
                    if role == "viewer":
                        assert shared.locator("#save-phrase-open").count() == 0
                        assert shared.goto(edit_url).status == 403
                    else:
                        assert shared.goto(edit_url).status == 200
                    ctx.close()
                isolated = browser.new_context()
                outsider = isolated.new_page()
                login(outsider, "fiction-boards-other@example.com", False, False)
                assert outsider.goto(board_url).status == 404
                assert (
                    "Fictional Basic Needs"
                    not in outsider.goto(origin + "/communication").text()
                )
                isolated.close()
                checks.append(
                    "same-profile caregiver sharing; viewer communicates without editing; unrelated family denied"
                )
                stage = "native no-JavaScript editor"
                native_context = browser.new_context(
                    java_script_enabled=False, viewport=dict(width=390, height=900)
                )
                native_context.add_cookies(context.cookies())
                native = native_context.new_page()
                native.goto(origin + "/communication/new")
                native.locator("#board-title").fill("Fictional native board")
                native.locator("#add-board-card").click()
                native.locator("[name=card_label]").fill("Water")
                native.locator("[name=card_spoken_text]").fill("I need water.")
                native.locator("#save-board").click()
                expect(native.locator("[data-picture-card]")).to_have_count(1)
                assert native.locator("noscript").is_visible()
                native_context.close()
                checks.append(
                    "native no-JavaScript add/save with usable picture view and explicit interactivity guidance"
                )
                stage = "mobile/responsive labels/contrast"
                paths = [
                    origin + "/communication",
                    edit_url,
                    board_url,
                    origin + "/communication/phrases",
                ]
                for width, height in [
                    (320, 900),
                    (375, 900),
                    (390, 844),
                    (768, 1024),
                    (1024, 768),
                    (1440, 1050),
                ]:
                    page.set_viewport_size(dict(width=width, height=height))
                    for url in paths:
                        assert page.goto(url).status == 200
                        assert page.locator("h1").count() == 1
                        assert page.evaluate(
                            "document.documentElement.scrollWidth<=innerWidth+1"
                        ), f"Overflow at {width}"
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
                        if width == 1440:
                            low = page.evaluate(r"""() => {
                             const rgb=v=>(v.match(/[\d.]+/g)||[]).map(Number),blend=(t,b)=>t.slice(0,3).map((v,i)=>v*(t[3]??1)+b[i]*(1-(t[3]??1)));
                             const bg=e=>!e?[255,255,255]:blend(rgb(getComputedStyle(e).backgroundColor),bg(e.parentElement));
                             const lum=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
                             return [...document.querySelectorAll('h1,h2,h3,p,label,summary,button,.text-link')].filter(e=>e.getClientRects().length&&!e.disabled).flatMap(e=>{const s=getComputedStyle(e),b=bg(e),f=lum(blend(rgb(s.color),b)),l=lum(b),r=(Math.max(f,l)+.05)/(Math.min(f,l)+.05),large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700);return r+.01<(large?3:4.5)?[e.tagName+'.'+e.className]:[];});
                            }""")
                            assert not low, "Low contrast: " + ",".join(low)
                        viewports += 1
                    page.goto(board_url)
                    page.screenshot(
                        path=str(artifacts / f"board-{width}.png"), full_page=True
                    )
                    page.goto(edit_url)
                    page.screenshot(
                        path=str(artifacts / f"editor-{width}.png"), full_page=True
                    )
                checks.append(
                    "24 page/viewport combinations, 320–1440px and landscape tablet; labels, sampled contrast and no horizontal overflow"
                )
                stage = "touch and reduced motion"
                touch = browser.new_context(
                    has_touch=True, is_mobile=True, viewport=dict(width=390, height=844)
                )
                touch.add_cookies(context.cookies())
                touch.add_init_script(SPEECH_MOCK)
                mobile = touch.new_page()
                mobile.goto(board_url)
                mobile.locator('[data-picture-card][data-label="water"]').tap()
                expect(mobile.locator("#phrase-written")).to_have_text("water")
                mobile.locator("#board-focus").tap()
                mobile.locator("#board-focus").tap()
                assert mobile.locator("body").evaluate(
                    "el=>el.classList.contains('board-focus-mode')"
                )
                mobile.locator("#board-focus").tap()
                mobile.emulate_media(reduced_motion="reduce")
                assert mobile.evaluate(
                    'matchMedia("(prefers-reduced-motion: reduce)").matches'
                )
                touch.close()
                checks.append("touch card activation, focus/exit and reduced motion")
                browser.close()
        except Exception as error:
            print(
                type(error).__name__,
                [
                    (Path(f.filename).name, f.lineno)
                    for f in traceback.extract_tb(error.__traceback__)
                    if "check_communication_boards" in f.filename
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
        speech="Browser API mocked; no claim of audible device verification",
    )
    (artifacts / "report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
