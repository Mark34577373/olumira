"""Real HTTPS browser signup; fictional data, local self-signed test server only."""
import json,logging,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import make_server
from test_public_experience import PublicExperienceTests as Fixture
from support import PASSWORD
from olumira.models import User
from olumira.extensions import db
from sqlalchemy import select


def main():
    Fixture.setUpClass();app=Fixture.app
    reproduce='--reproduce' in sys.argv
    if reproduce:
        def override_policy(response):
            response.headers['Referrer-Policy']='no-referrer'
            return response
        # Flask executes after-request handlers in reverse registration order.
        app.after_request_funcs[None].insert(0,override_policy)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    logging.getLogger('flask_wtf.csrf').setLevel(logging.INFO)
    logging.getLogger('flask_wtf.csrf').addHandler(logging.StreamHandler())
    server=make_server('127.0.0.1',0,app,threaded=True,ssl_context='adhoc')
    origin=f'https://127.0.0.1:{server.server_port}'
    app.config.update(APP_ENV='production',PUBLIC_APP_URL=origin,SESSION_COOKIE_SECURE=True,SESSION_COOKIE_NAME='__Host-olumira_session')
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            for width in (375,1440):
                context=browser.new_context(ignore_https_errors=True,viewport={'width':width,'height':950})
                page=context.new_page();email=f'fictional-https-{width}@example.com'
                response=page.goto(origin+'/auth/register')
                policy=response.headers.get('referrer-policy')
                page.locator('#display_name').fill('Fictional HTTPS caregiver')
                page.locator('#email').fill(email)
                page.locator('#password').fill(PASSWORD);page.locator('#confirm_password').fill(PASSWORD)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/auth/register')) as received:
                    page.get_by_role('button',name='Create account',exact=True).click()
                request=received.value.request
                keys=sorted(__import__('urllib.parse',fromlist=['parse_qs']).parse_qs(request.post_data or '').keys())
                print(json.dumps(dict(width=width,policy=policy,status=received.value.status,field_names=keys,has_referer='referer' in request.all_headers())),flush=True)
                if reproduce:
                    assert received.value.status==400
                    with app.app_context():assert db.session.scalar(select(User).where(User.email==email)) is None
                    context.close();continue
                assert received.value.status==302, page.locator('main').inner_text()
                expect(page).to_have_url(origin+'/auth/check-email')
                with app.app_context():
                    user=db.session.scalar(select(User).where(User.email==email));assert user is not None and not user.email_verified
                    assert user.password_hash!=PASSWORD
                context.close()
            browser.close()
        print('REPRODUCED: former no-referrer policy rejects valid HTTPS signup without creating accounts.' if reproduce else 'PASS: mobile/desktop real HTTPS native registration, secure session, CSRF, persisted hashed accounts.')
    finally:server.shutdown();Fixture.tearDownClass()

if __name__=='__main__':main()
