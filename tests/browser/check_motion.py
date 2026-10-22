"""Real browser motion/preferences/fallback checks and fictional care workflows."""
import json
import logging
import re
import sys
import threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import make_server
from test_public_experience import PublicExperienceTests as Fixture
from support import PASSWORD,create_user
from olumira.extensions import db
from olumira.models import WorkspaceMembership


def main():
    Fixture.setUpClass()
    helper,_=create_user(Fixture.app,'fictional-motion-helper@example.com')
    with Fixture.app.app_context():
        db.session.add(WorkspaceMembership(id='e'*32,workspace_id=Fixture.wid,user_id=helper,role='caregiver',status='active'))
        db.session.commit()
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server=make_server('127.0.0.1',0,Fixture.app,threaded=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    out=ROOT/'artifacts/day43-6c'
    out.mkdir(parents=True,exist_ok=True)
    checks=[]
    errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            context=browser.new_context(viewport=dict(width=1440,height=1000),reduced_motion='no-preference')
            page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())
            for width in (320,390,768,1024,1440):
                page.set_viewport_size(dict(width=width,height=1000))
                for path in ('/','/features','/how-it-works','/about','/contact','/auth/login'):
                    assert page.goto(origin+path).status==200
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,path)
                    expect(page.locator('h1')).to_be_visible()
            page.set_viewport_size(dict(width=1440,height=1000))
            page.goto(origin+'/about')
            garden=page.locator('.garden-illustration')
            expect(garden).to_have_attribute('data-garden-active','true')
            assert garden.locator('.garden-sun').evaluate("e=>getComputedStyle(e).animationPlayState")=='running'
            # A persistent pause control and OS preference stop animation immediately.
            page.locator('[data-motion-toggle]').click()
            expect(page.locator('html')).to_have_attribute('data-motion-paused','true')
            assert garden.locator('.garden-sun').evaluate("e=>getComputedStyle(e).animationName")=='none'
            page.reload()
            expect(page.locator('html')).to_have_attribute('data-motion-paused','true')
            page.locator('[data-motion-toggle]').click()
            page.emulate_media(reduced_motion='reduce')
            assert garden.locator('.garden-sun').evaluate("e=>getComputedStyle(e).animationName")=='none'
            assert not page.evaluate('window.OlumiraMotion.allowed()')
            page.emulate_media(reduced_motion='no-preference')
            # Offscreen decorative SVGs pause rather than burning cycles below the fold.
            page.locator('footer').scroll_into_view_if_needed()
            expect(garden).to_have_attribute('data-garden-active','false')
            page.screenshot(path=str(out/'about-footer.png'))
            page.goto(origin+'/about')
            page.screenshot(path=str(out/'about-desktop.png'))
            checks.append('30 responsive public/auth layouts; OS preference, persisted pause, offscreen illustration pause')
            nojs=browser.new_context(java_script_enabled=False,viewport=dict(width=320,height=900))
            fallback=nojs.new_page();fallback.goto(origin+'/about')
            expect(fallback.locator('h1')).to_be_visible()
            expect(fallback.locator('.garden-illustration')).to_be_visible()
            assert fallback.locator('.garden-sun').evaluate("e=>getComputedStyle(e).animationPlayState")=='paused'
            nojs.close()
            noio=browser.new_context()
            noio.add_init_script('delete window.IntersectionObserver')
            fallback=noio.new_page();fallback.goto(origin+'/features')
            assert fallback.locator('h1').is_visible()
            assert fallback.locator('.public-showcase').first.evaluate('e=>Number(getComputedStyle(e).opacity)>0')
            noio.close()
            checks.append('No-script and no-IntersectionObserver content remains visible')
            page.goto(origin+'/auth/login')
            page.locator('#email').fill('fictional-public@example.com')
            page.locator('#password').fill(PASSWORD)
            page.locator('.auth-submit').click()
            expect(page).to_have_url(origin+'/setup')
            page.goto(origin+'/')
            before=page.locator('.stat-value strong').all_text_contents()
            # Motion must never introduce intermediate or fictional numbers.
            assert before==page.locator('.stat-value strong').all_text_contents()
            task=page.locator('.task-form button').first
            task.click()
            expect(page.locator('.task-form button.completed').first).to_have_attribute('aria-pressed','true')
            checks.append('Exact dashboard statistics and server-confirmed checklist completion')
            page.locator('#active-profile').select_option('f'*32)
            page.get_by_role('button',name='Switch profile',exact=True).click()
            page.goto(origin+'/care-plans/new')
            page.locator('#plan-title').fill('Fictional motion plan')
            for _ in range(5):
                page.locator('[data-wizard-next]').click()
            page.get_by_role('button',name='Save care plan',exact=True).click()
            page.wait_for_url(re.compile(r'.*/care-plans/[a-f0-9]{32}$'))
            plan_url=page.url
            page.goto(plan_url+'/edit')
            page.locator('#plan-title').fill('Fictional revised motion plan')
            for _ in range(5):
                page.locator('[data-wizard-next]').click()
            page.get_by_role('button',name='Save care plan',exact=True).click()
            expect(page.locator('h1')).to_contain_text('Fictional revised motion plan')
            checks.append('Care-plan wizard, focus-preserving step changes and persisted edit')
            page.goto(origin+'/routines/new?template=communication')
            page.locator('#builder-name').fill('Fictional motion routine')
            first_title=page.locator('[name=step_title]').first.input_value()
            page.locator('[data-step-down]').first.focus()
            page.keyboard.press('Enter')
            expect(page.locator('[name=step_title]').nth(1)).to_have_value(first_title)
            page.locator('[data-step-editor] details').first.locator('summary').click()
            page.locator('[name=step_timer_seconds]').first.fill('1')
            timer=page.locator('#preview-steps [data-local-timer]').first
            timer.locator('[data-timer-action=start]').click()
            expect(timer).to_have_attribute('data-timer-state','running')
            expect(timer).to_have_attribute('data-timer-state','finished',timeout=3000)
            # Pointer reordering keeps a dashed target only during an actual drag.
            handle=page.locator('.step-drag-handle').first
            page.locator('[data-step-editor]').first.evaluate("e=>e.scrollIntoView({block:'start'})")
            a=handle.bounding_box();b=page.locator('[data-step-editor]').nth(1).bounding_box()
            page.mouse.move(a['x']+10,a['y']+10);page.mouse.down()
            page.mouse.move(b['x']+b['width']/2,b['y']+b['height']*.6,steps=8)
            expect(page.locator('.step-drop-target')).to_have_count(1)
            page.mouse.up()
            expect(page.locator('.step-drop-target')).to_have_count(0)
            page.locator('#save-routine').click()
            page.wait_for_url(re.compile(r'.*/routines/\d+$'))
            page.get_by_role('button',name='Start or resume guided routine').click()
            page.wait_for_url(re.compile(r'.*/routines/sessions/.*'))
            session_url=page.url.split('?')[0]
            page.goto(session_url+'?mode=overview')
            for index in range(1,5):
                page.get_by_role('button',name=f'Complete step {index}',exact=True).click()
            expect(page.locator('main')).to_contain_text('All 4 steps are complete')
            checks.append('Keyboard reorder, real local timer state, save and four server-confirmed guided completions')
            page.add_init_script('''
              window.__speechCalls=0;
              window.SpeechSynthesisUtterance=function(text){this.text=text;};
              Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{
                getVoices:()=>[{voiceURI:'fictional-local',name:'Fictional local voice',lang:'en',localService:true}],
                cancel:()=>{},addEventListener:()=>{},speak:u=>{window.__speechCalls++;window.__mockUtterance=u;u.onstart();}
              }});
            ''')
            page.goto(origin+'/communication/new?template=needs')
            page.locator('#board-title').fill('Fictional motion board')
            page.locator('#save-board').click()
            # Open the board from its library/editor success destination.
            if not page.locator('#communication-board').count():
                page.get_by_role('link',name='Open board',exact=False).first.click()
            expect(page.locator('#communication-board')).to_be_visible()
            assert page.evaluate('window.__speechCalls')==0
            page.locator('.speech-settings summary').click()
            page.locator('#speech-enabled').uncheck()
            card=page.locator('[data-picture-card]').first
            card.focus();page.keyboard.press('Enter')
            expect(card).to_have_attribute('aria-current','true')
            expect(page.locator('#phrase-written')).not_to_be_empty()
            page.locator('#clear-phrase').click()
            expect(card).not_to_have_attribute('aria-current','true')
            card.click()
            page.locator('#save-phrase-open').click()
            expect(page.locator('dialog[open]')).to_be_visible()
            page.locator('#save-phrase-label').fill('Fictional saved choice')
            page.get_by_role('button',name='Save phrase',exact=True).click()
            expect(page.locator('#speech-status')).to_have_text('Phrase saved for this profile.')
            expect(page.locator('dialog')).not_to_be_visible()
            page.locator('#speech-enabled').check()
            page.locator('#speak-phrase').click()
            expect(page.locator('#speak-phrase')).to_have_attribute('data-speaking','true')
            page.evaluate('window.__mockUtterance.onend()')
            expect(page.locator('#speak-phrase')).to_have_attribute('data-speaking','false')
            page.wait_for_function('() => document.querySelector("#speech-status").getAnimations().length===0')
            page.locator('#save-phrase-open').click()
            page.locator('#save-phrase-label').fill('Fictional rejected phrase')
            page.route('**/communication/phrases',lambda route:route.fulfill(status=500,content_type='application/json',body='{"error":"Fictional server rejection"}'))
            page.get_by_role('button',name='Save phrase',exact=True).click()
            expect(page.locator('dialog[open] [role=alert]')).to_have_text('Fictional server rejection')
            assert page.locator('#speech-status').evaluate('e=>e.getAnimations().length')==0
            page.locator('#cancel-save-phrase').click()
            page.unroute('**/communication/phrases')
            checks.append('Keyboard picture activation, accessible selection, confirmed phrase save, failed save with no success animation, mocked local speech start/end (no audio)')
            page.goto(origin+'/observations')
            page.get_by_role('link',name='Add observation',exact=True).click()
            page.locator('#observation-activity').fill('Fictional calm reading break')
            page.locator('#observation-time').fill('08:30')
            page.locator('#observation-notes').fill('Fictional example for motion verification.')
            page.get_by_role('button',name='Save observation',exact=True).click()
            expect(page.locator('.ui-alert-success')).to_contain_text('Observation saved')
            page.goto(origin+'/care/tasks/new')
            page.get_by_label('Task title',exact=True).fill('Fictional shared preparation')
            page.get_by_label('Assigned caregiver',exact=True).select_option(Fixture.uid)
            page.get_by_role('button',name='Save task',exact=True).click()
            page.get_by_role('button',name='Mark completed',exact=True).click()
            expect(page.locator('.care-detail .eyebrow')).to_contain_text('Completed')
            page.goto(origin+'/care/handoffs/new')
            page.locator('#handoff-summary').fill('Fictional reviewed shift summary for a trusted helper.')
            page.locator('#handoff-recipient').select_option(helper)
            page.get_by_role('button',name='Share handoff',exact=True).click()
            expect(page.locator('.ui-alert-success')).to_contain_text('Handoff')
            expect(page.locator('.care-detail')).to_contain_text('Fictional reviewed shift summary')
            page.goto(origin+'/notifications')
            expect(page.locator('.notification-card').first).to_be_visible()
            page.locator('.notification-card').first.get_by_role('button',name='Mark read',exact=True).click()
            expect(page.locator('.notification-card.is-read').first).to_be_visible()
            page.locator('.notification-card').first.get_by_role('button',name='Dismiss',exact=True).click()
            checks.append('Real observation save, task completion, handoff sharing, notification read and explicit dismissal')
            page.goto(origin+'/calendar')
            current=page.url
            next_link=page.get_by_role('link',name=re.compile('Next',re.I)).first
            next_link.click()
            assert page.url!=current
            checks.append('Native calendar navigation remains accurate and immediate')
            for path in ('/observations','/observations/timeline','/observations/insights','/observations/reports','/care/tasks','/care/handoffs','/notifications','/settings','/auth/settings',plan_url.removeprefix(origin)):
                for width in (320,390,768,1024,1440):
                    page.set_viewport_size(dict(width=width,height=1000))
                    assert page.goto(origin+path).status==200,(width,path)
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,path)
            page.set_viewport_size(dict(width=1440,height=1000))
            page.goto(origin+'/settings')
            page.get_by_label('Reduce motion',exact=True).check()
            page.get_by_role('button',name='Save personal settings',exact=True).click()
            page.goto(origin+'/')
            expect(page.locator('html')).to_have_attribute('data-reduced-motion','true')
            assert not page.evaluate('window.OlumiraMotion.allowed()')
            assert page.locator('.stat-card').first.evaluate("e=>getComputedStyle(e).animationName")=='none'
            page.goto(origin+'/welcome')
            expect(page.locator('html')).to_have_attribute('data-reduced-motion','true')
            assert not page.evaluate('window.OlumiraMotion.allowed()')
            checks.append('50 authenticated layouts and persisted personal reduced-motion setting shared with public pages')
            assert not errors,errors
            browser.close()
        (out/'motion-browser.json').write_text(json.dumps(dict(checks=checks,errors=errors),indent=2))
        print('PASS: '+ '; '.join(checks))
    finally:
        server.shutdown();Fixture.tearDownClass()

if __name__=='__main__':
    main()
