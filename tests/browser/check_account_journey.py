"""Actual registration, verification, onboarding, return, reset and app journey."""
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
from test_account_recovery import email_link
from support import PASSWORD
from olumira.models import User,OnboardingState
from olumira.extensions import db


def main():
    Fixture.setUpClass()
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server=make_server('127.0.0.1',0,Fixture.app,threaded=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    Fixture.app.config['PUBLIC_APP_URL']=origin
    artifacts=ROOT/'artifacts/day43-6'
    artifacts.mkdir(parents=True,exist_ok=True)
    layouts=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(reduced_motion='reduce')
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            for width in (320,375,390,768,1024,1280,1440):
                page.set_viewport_size(dict(width=width,height=1000))
                for path in ('/auth/login','/auth/register','/auth/forgot-password','/auth/resend-verification','/auth/verify-email','/auth/reset-password'):
                    assert page.goto(origin+path).status==200
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,path)
                    expect(page.locator('h1')).to_be_visible()
                    if width in (390,1440) and path in ('/auth/login','/auth/register'):
                        page.screenshot(path=str(artifacts/f'{width}-{path.split("/")[-1]}.png'))
                    layouts.append(dict(width=width,path=path))
            page.set_viewport_size(dict(width=1440,height=1000))
            page.goto(origin+'/')
            page.get_by_role('navigation',name='Public navigation').get_by_role('link',name='Get Started',exact=True).click()
            page.locator('#display_name').fill('Fictional Robin')
            email='fictional-browser-journey@example.com'
            page.locator('#email').fill(email)
            page.locator('#password').fill(PASSWORD)
            page.locator('#confirm_password').fill(PASSWORD)
            page.get_by_role('button',name='Create account',exact=True).click()
            expect(page).to_have_url(origin+'/auth/check-email')
            page.goto(origin+'/auth/login')
            page.locator('#email').fill(email)
            page.locator('#password').fill(PASSWORD)
            page.get_by_role('button',name='Sign in',exact=True).click()
            expect(page).to_have_url(origin+'/auth/verification')
            expect(page.get_by_role('heading',name='Verify your email',exact=True)).to_be_visible()
            code,_,_=email_link(Fixture.app,'verify_email')
            page.goto(origin+'/auth/verify-email#token='+code)
            page.get_by_role('button',name='Verify email',exact=True).click()
            expect(page.get_by_role('heading',name='Email verified',exact=True)).to_be_visible()
            page.goto(origin+'/auth/login')
            page.locator('#email').fill(email)
            page.locator('#password').fill(PASSWORD)
            page.locator('[data-password-toggle]').click()
            expect(page.locator('#password')).to_have_attribute('type','text')
            page.locator('[data-password-toggle]').click()
            page.get_by_role('button',name='Sign in',exact=True).click()
            expect(page).to_have_url(origin+'/setup')
            page.get_by_role('button',name='Get started',exact=True).click()
            page.get_by_role('button',name='Save and continue',exact=True).click()
            page.locator('[name=profile_action]').select_option('new')
            page.locator('[name=profile_name]').fill('Fictional Willow')
            page.get_by_role('button',name='Save and continue',exact=True).click()
            page.locator('[name=routine_id]').select_option('')
            page.get_by_role('button',name='Save and continue',exact=True).click()
            page.get_by_role('button',name='Save and continue',exact=True).click()
            page.get_by_role('button',name='Skip this optional step',exact=True).click()
            expect(page.get_by_role('link',name='Explore Care Plans',exact=True)).to_have_attribute('href','/care-plans')
            page.get_by_role('button',name='Finish setup',exact=True).click()
            expect(page.get_by_role('link',name='Enter Olumira',exact=True)).to_be_visible()
            with Fixture.app.app_context():
                user=db.session.scalar(db.select(User).where(User.email==email))
                state=db.session.get(OnboardingState,(user.id,user.owner_id))
                assert state.completed_at and state.profile_id and state.routine_id and state.board_id
            for width in (320,375,390,768,1024,1280,1440):
                page.set_viewport_size(dict(width=width,height=1000))
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('setup',width)
            page.get_by_role('link',name='Enter Olumira',exact=True).click()
            expect(page).to_have_url(origin+'/')
            expect(page.locator('#active-profile')).to_contain_text('Fictional Willow')
            expect(page.locator('#active-profile option:checked')).to_have_text('Fictional Willow')
            expect(page.locator('#primary-links')).to_be_visible()
            for width in (320,375,390,768,1024,1280,1440):
                page.set_viewport_size(dict(width=width,height=1000))
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('dashboard',width)
            page.goto(origin+'/routines')
            expect(page.locator('h1')).to_be_visible()
            page.goto(origin+'/auth/settings')
            expect(page.get_by_role('heading',name='Account & security',exact=True)).to_be_visible()
            page.locator('.account-menu').last.locator('summary').click()
            page.get_by_role('button',name='Sign out',exact=True).click()
            page.goto(origin+'/auth/login')
            page.locator('#email').fill(email)
            page.locator('#password').fill(PASSWORD)
            page.get_by_role('button',name='Sign in',exact=True).click()
            expect(page).to_have_url(origin+'/')
            # Log out before requesting a password reset.
            page.locator('.account-menu').last.locator('summary').click()
            page.get_by_role('button',name='Sign out',exact=True).click()
            page.goto(origin+'/auth/forgot-password')
            page.locator('#email').fill(email)
            page.locator('form.auth-form button[type=submit]').click()
            code,_,_=email_link(Fixture.app,'reset_password')
            page.goto(origin+'/auth/reset-password#token='+code)
            new_password='Fictional refreshed cedar passphrase 84'
            page.locator('#password').fill(new_password)
            page.locator('#confirm_password').fill(new_password)
            page.locator('form.auth-form button[type=submit]').click()
            expect(page.get_by_role('heading',name='Password reset',exact=True)).to_be_visible()
            page.goto(origin+'/auth/login')
            page.locator('#email').fill(email)
            page.locator('#password').fill(new_password)
            page.get_by_role('button',name='Sign in',exact=True).click()
            expect(page).to_have_url(origin+'/')
            assert not errors,errors
            browser.close()
        (artifacts/'account-browser.json').write_text(json.dumps(dict(layouts=layouts,journey='pass',js_errors=errors),indent=2))
        print('PASS: 42 auth layouts; actual register → verify → login → seven saved setup steps → dashboard/profile → feature → account → logout → returning login → reset → login. No external mail sent.')
    finally:
        server.shutdown()
        Fixture.tearDownClass()

if __name__=='__main__':
    main()
