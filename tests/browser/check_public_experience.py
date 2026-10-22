"""Public website responsive / menu checks. Uses an isolated fictional database."""
import json
import logging
import sys
import threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import make_server
from test_public_experience import PublicExperienceTests as Fixture
from check_targeted_ui import contrast


def main():
    Fixture.setUpClass()
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server=make_server('127.0.0.1',0,Fixture.app,threaded=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    artifacts=ROOT/'artifacts/day43-6'
    artifacts.mkdir(parents=True,exist_ok=True)
    results=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(reduced_motion='reduce')
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            for width in (320,375,390,768,1024,1280,1440):
                page.set_viewport_size(dict(width=width,height=1000))
                for path in ('/','/features','/how-it-works','/about','/contact','/privacy','/terms'):
                    response=page.goto(origin+path)
                    assert response.status==200,(width,path,response.status)
                    if not page.evaluate('document.documentElement.scrollWidth<=innerWidth'):
                        page.screenshot(path=str(artifacts/'overflow.png'),full_page=True)
                        print(page.evaluate("Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.className,e.getBoundingClientRect().width]).slice(0,20)"),flush=True)
                        raise AssertionError((width,path,'overflow'))
                    expect(page.locator('h1')).to_be_visible()
                    if path=='/how-it-works':
                        expect(page.locator('h1')).to_have_text('From your first step to your everyday rhythm.')
                    for button in page.locator('.public-button').all():
                        if button.is_visible() and button.is_enabled():
                            assert contrast(button)>=4.5,(width,path,'button contrast')
                    menu=page.get_by_role('button',name='Menu')
                    if width<=900:
                        expect(menu).to_be_visible()
                        expect(page.locator('#public-navigation')).to_be_hidden()
                        menu.click()
                        expect(menu).to_have_attribute('aria-expanded','true')
                        expect(page.locator('#public-navigation')).to_be_visible()
                        page.locator('.public-links a').first.focus()
                        page.keyboard.press('Escape')
                        expect(menu).to_be_focused()
                        expect(menu).to_have_attribute('aria-expanded','false')
                        assert not page.locator('#public-navigation').evaluate('e=>e.contains(document.activeElement)')
                    if width in (390,1440):
                        page.screenshot(path=str(artifacts/f'{width}-{path.strip("/") or "home"}.png'))
                    results.append(dict(width=width,path=path,status='pass'))
            # Menu state follows resize, and no-script visitors retain navigation.
            page.set_viewport_size(dict(width=390,height=1000))
            page.goto(origin+'/')
            page.get_by_role('button',name='Menu').click()
            page.locator('.public-links a').first.focus()
            page.set_viewport_size(dict(width=1024,height=1000))
            expect(page.locator('#public-navigation')).to_be_visible()
            page.set_viewport_size(dict(width=390,height=1000))
            expect(page.get_by_role('button',name='Menu')).to_be_focused()
            expect(page.locator('#public-navigation')).to_be_hidden()
            nojs=browser.new_context(java_script_enabled=False,viewport=dict(width=320,height=900))
            fallback=nojs.new_page()
            fallback.goto(origin+'/')
            expect(fallback.locator('#public-navigation')).to_be_visible()
            expect(fallback.get_by_role('navigation',name='Public navigation').get_by_role('link',name='Features',exact=True)).to_be_visible()
            assert fallback.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
            nojs.close()
            browser.close()
        (artifacts/'public-browser.json').write_text(json.dumps(dict(layouts=results,js_errors=errors,menu='pass',no_script='pass'),indent=2))
        print(f'PASS: {len(results)} public layouts, mobile toggle/Escape/focus/resize, no-script fallback; no JavaScript errors.')
    finally:
        server.shutdown()
        Fixture.tearDownClass()

if __name__=='__main__':
    main()
