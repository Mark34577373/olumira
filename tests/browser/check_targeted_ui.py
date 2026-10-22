"""Real-browser regression for care CTA contrast and saved-setup action layout."""
import logging
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from flask_migrate import upgrade
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from olumira import create_app
from olumira.extensions import db
from support import PASSWORD, create_user


def contrast(locator):
    return locator.evaluate('''el => {
      const s=getComputedStyle(el);
      const luminance=color=>{
        const rgb=color.match(/[\\d.]+/g).slice(0,3).map(Number).map(v=>{
          v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;
        });return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
      };
      const a=luminance(s.color),b=luminance(s.backgroundColor);
      return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    }''')


def main():
    with tempfile.TemporaryDirectory() as folder:
        app=create_app(dict(APP_ENV='testing',DATABASE=str(Path(folder)/'ui.db')))
        with app.app_context():
            upgrade()
        create_user(app,'fictional-targeted-ui@example.com')
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        server=make_server('127.0.0.1',0,app,threaded=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        origin=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                page=browser.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce')
                page.goto(origin+'/auth/login')
                page.locator('#email').fill('fictional-targeted-ui@example.com')
                page.locator('#password').fill(PASSWORD)
                page.locator('.auth-submit').click()
                expect(page).to_have_url(origin+'/setup')
                page.goto(origin+'/care/tasks')
                cta=page.get_by_role('link',name='Share a responsibility',exact=True)
                expect(cta).to_be_visible()
                assert contrast(cta)>=4.5
                cta.hover()
                assert contrast(cta)>=4.5
                cta.focus()
                page.keyboard.press('Tab')
                page.keyboard.press('Shift+Tab')
                assert cta.evaluate("e=>e.matches(':focus-visible') && getComputedStyle(e).outlineStyle!=='none'")
                cta.click()
                assert '/care/tasks/' in page.url
                page.goto(origin+'/setup')
                page.get_by_role('button',name='Skip setup for now',exact=True).click()
                page.goto(origin+'/setup')
                group=page.locator('.onboarding-actions')
                enter=group.get_by_role('link',name='Enter Olumira',exact=True)
                tour=group.get_by_role('link',name='Take the product tour',exact=True)
                revisit=group.get_by_role('button',name='Revisit setup',exact=True)
                expect(enter).to_have_attribute('href','/')
                expect(tour).to_have_attribute('href','/tour')
                for width in (1440,768,390,320):
                    page.set_viewport_size(dict(width=width,height=1000))
                    assert contrast(enter)>=4.5 and contrast(revisit)>=4.5
                    boxes=[x.bounding_box() for x in (enter,tour,revisit)]
                    for i,a in enumerate(boxes):
                        for b in boxes[i+1:]:
                            horizontal=max(b['x']-a['x']-a['width'],a['x']-b['x']-b['width'])
                            vertical=max(b['y']-a['y']-a['height'],a['y']-b['y']-b['height'])
                            assert max(horizontal,vertical)>=12-0.5,(width,a,b)
                    assert group.evaluate('e=>e.scrollWidth<=e.clientWidth')
                enter.focus()
                page.keyboard.press('Tab')
                expect(tour).to_be_focused()
                page.keyboard.press('Tab')
                expect(revisit).to_be_focused()
                assert revisit.evaluate("e=>e.matches(':focus-visible') && getComputedStyle(e).outlineStyle!=='none'")
                revisit.click()
                expect(page.get_by_role('button',name='Get started',exact=True)).to_be_visible()
                browser.close()
            print('PASS: care CTA normal/hover contrast and focus; setup contrast, spacing at four widths, keyboard order, destinations and restart submission.')
        finally:
            server.shutdown()
            with app.app_context():
                db.engine.dispose()


if __name__=='__main__':
    main()
