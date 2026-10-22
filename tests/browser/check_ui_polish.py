"""Day43.6D: real checklist failure/retry, explicit context, route/layout sweep."""
import json,logging,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import make_server
from test_public_experience import PublicExperienceTests as Fixture
from support import PASSWORD
from olumira.extensions import db
from olumira.models import FamilyWorkspace,CareProfile
from services.workspaces import create_workspace
from services.database import transaction
from check_targeted_ui import contrast


def main():
    Fixture.setUpClass()
    with Fixture.app.app_context():
        workspace=db.session.get(FamilyWorkspace,Fixture.wid)
        workspace.name='Fictional Cedar Family · '+('Connected care '*5)[:55]
        profile=db.session.get(CareProfile,'f'*32)
        profile.display_name='Fictional '+('LongProfileName'*5)
        db.session.commit()
        with transaction():
            second=create_workspace(Fixture.uid,'Fictional second family workspace')
            second_id=second.id
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server=make_server('127.0.0.1',0,Fixture.app,threaded=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    out=ROOT/'artifacts/day43-6d';out.mkdir(parents=True,exist_ok=True)
    layouts=[];errors=[];checks=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport=dict(width=1440,height=1100),reduced_motion='no-preference')
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())
            public=('/','/features','/how-it-works','/about','/contact','/privacy','/terms','/auth/login','/auth/register')
            for width in (320,375,430,768,1024,1440):
                page.set_viewport_size(dict(width=width,height=1100))
                for path in public:
                    assert page.goto(origin+path).status==200
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,path)
                    expect(page.locator('h1')).to_be_visible()
                    layouts.append(dict(path=path,width=width,session='anonymous'))
            page.set_viewport_size(dict(width=1440,height=1100))
            page.goto(origin+'/auth/login');page.locator('#email').fill('fictional-public@example.com');page.locator('#password').fill(PASSWORD);page.locator('.auth-submit').click()
            page.goto(origin+'/')
            # Browsing choices never changes the active context or writes a request.
            summary=page.locator('.context-current').inner_text()
            page.locator('#active-profile').select_option('f'*32)
            expect(page.locator('.context-current')).to_have_text(summary)
            expect(page.locator('[data-checklist]')).to_have_attribute('data-profile','')
            page.get_by_role('button',name='Switch profile',exact=True).click()
            expect(page.locator('[data-checklist]')).to_have_attribute('data-profile','f'*32)
            page.locator('#active-profile').select_option('');page.get_by_role('button',name='Switch profile',exact=True).click()
            original=page.locator('.context-current').inner_text()
            page.locator('#active-workspace').select_option(second_id)
            expect(page.locator('.context-current')).to_have_text(original)
            expect(page.locator('[data-checklist]')).to_have_attribute('data-workspace',Fixture.wid)
            page.get_by_role('button',name='Switch workspace',exact=True).click()
            expect(page.locator('[data-checklist]')).to_have_attribute('data-workspace',second_id)
            page.locator('#active-workspace').select_option(Fixture.wid);page.get_by_role('button',name='Switch workspace',exact=True).click()
            checks.append('Long context labels; selection remains staged until explicit authorized POST')
            # In-place save does not navigate, steal focus or optimistically mark completion.
            page.evaluate('window.__polishMarker=true')
            first=page.locator('.task-form').first;control=first.locator('button');path=first.get_attribute('action')
            pending=[]
            page.route('**'+path,lambda route:pending.append(route))
            control.focus();page.keyboard.press('Enter')
            expect(first).to_have_attribute('aria-busy','true')
            expect(page.get_by_role('button',name='Switch workspace',exact=True)).to_be_disabled()
            expect(control).to_have_attribute('aria-pressed','false')
            expect(page.locator('#checklist-status')).to_contain_text('Saving')
            pending.pop().continue_();page.unroute('**'+path)
            expect(control).to_have_attribute('aria-pressed','true')
            expect(control).to_be_focused()
            expect(page.get_by_role('button',name='Switch workspace',exact=True)).to_be_enabled()
            expect(page.locator('#checklist-status')).to_contain_text('Saved. 1 of 5')
            expect(page.locator('[data-checklist-stat]')).to_have_text('20%')
            assert page.evaluate('window.__polishMarker')
            assert page.evaluate("sessionStorage.getItem('olumira.routineScrollY')===null")
            # Rejected request leaves the previous confirmed state visible.
            page.route('**'+path,lambda route:route.fulfill(status=500,content_type='application/json',body='{}'))
            control.click()
            expect(page.locator('#checklist-status')).to_have_attribute('role','alert')
            expect(control).to_have_attribute('aria-pressed','true')
            expect(page.locator('[data-checklist-stat]')).to_have_text('20%')
            expect(page.locator('[data-checklist-reload]')).to_be_visible()
            page.unroute('**'+path)
            control.click();expect(control).to_have_attribute('aria-pressed','false')
            # Simulate a committed response lost in transit; retry must not toggle it back.
            def lost(route):
                response=route.fetch()
                assert response.status==200
                route.abort('failed')
            page.route('**'+path,lost)
            control.click();expect(page.locator('#checklist-status')).to_have_attribute('role','alert')
            expect(control).to_have_attribute('aria-pressed','false')
            page.unroute('**'+path)
            control.click();expect(control).to_have_attribute('aria-pressed','true')
            expect(page.locator('#checklist-status')).to_contain_text('Saved. 1 of 5')
            checks.append('Pending/confirmed/failed checklist; keyboard focus; no reload; safe retry after lost committed response')
            # Exact 100% still fits at mobile widths; all six quick actions resolve.
            for item in page.locator('.task-form button').all():
                if item.get_attribute('aria-pressed')=='false':
                    item.click();expect(item).to_have_attribute('aria-pressed','true')
            expect(page.locator('[data-checklist-stat]')).to_have_text('100%')
            for link in page.locator('.quick-actions a').all():
                response=page.request.get(origin+link.get_attribute('href'))
                assert response.status==200
            # Empty care CTA retains white text and valid contrast.
            page.goto(origin+'/care/tasks')
            cta=page.get_by_role('link',name='Share a responsibility',exact=True)
            assert contrast(cta)>=4.5
            cta.hover();assert contrast(cta)>=4.5
            checks.append('All six quick actions and care empty-state normal/hover contrast')
            # Review every registered static GET HTML route, including settings subpages.
            routes=sorted({r.rule for r in Fixture.app.url_map.iter_rules() if 'GET' in r.methods and '<' not in r.rule and not r.rule.startswith('/health') and r.rule!='/robots.txt'})
            for width in (320,375,430,768,1024,1440):
                page.set_viewport_size(dict(width=width,height=1100))
                for path in routes:
                    response=page.goto(origin+path)
                    assert response.status==200,(width,path,response.status)
                    if 'text/html' not in response.headers.get('content-type',''):continue
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,path)
                    expect(page.locator('h1')).to_be_visible()
                    layouts.append(dict(path=path,width=width,session='authenticated'))
                page.goto(origin+'/')
                heights=page.locator('.stats-grid>.stat-card').evaluate_all('els=>els.map(e=>e.getBoundingClientRect().height)')
                assert max(heights)-min(heights)<1,(width,heights)
                for button in page.locator('.workspace-context button,.workspace-context select').all():
                    assert button.bounding_box()['height']>=44
                if width in (320,375,1440):
                    page.screenshot(path=str(out/f'dashboard-{width}.png'))
                    page.locator('.workspace-context').screenshot(path=str(out/f'context-{width}.png'))
                    page.locator('.stats-grid').screenshot(path=str(out/f'stats-{width}.png'))
            # Escape closes the current popover and returns focus to its trigger.
            menu=page.locator('.account-menu').last
            menu.locator('summary').click();menu.get_by_role('link',name='My account',exact=True).focus();page.keyboard.press('Escape')
            expect(menu).not_to_have_attribute('open','')
            expect(menu.locator('summary')).to_be_focused()
            page.emulate_media(reduced_motion='reduce');page.goto(origin+'/')
            assert page.locator('.garden-sun').evaluate("e=>getComputedStyle(e).animationName")=='none'
            assert not page.evaluate('window.OlumiraMotion.allowed()')
            checks.append('Static-route rendered review at six widths; equal statistic heights; 44px controls; popover focus; reduced motion')
            # With scripts disabled, the new native desired-state form still persists.
            context=browser.new_context(java_script_enabled=False,storage_state=page.context.storage_state(),viewport=dict(width=375,height=1100))
            fallback=context.new_page();fallback.goto(origin+'/')
            button=fallback.locator('.task-form button').first
            expected='false' if button.get_attribute('aria-pressed')=='true' else 'true'
            button.click();expect(fallback.locator('.task-form button').first).to_have_attribute('aria-pressed',expected)
            context.close()
            checks.append('No-JavaScript native checklist fallback')
            assert not errors,errors
            browser.close()
        (out/'ui-browser.json').write_text(json.dumps(dict(layouts=layouts,checks=checks,errors=errors),indent=2))
        print(f'PASS: {len(layouts)} rendered route/layout checks; '+ '; '.join(checks))
    finally:
        server.shutdown();Fixture.tearDownClass()

if __name__=='__main__':main()
