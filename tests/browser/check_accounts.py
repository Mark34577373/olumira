"""Real browser account recovery/settings tests, with a private synthetic inbox."""
import json
import logging
import sys
import tempfile
import threading
from urllib.parse import urlsplit
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from flask_migrate import upgrade
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from olumira import create_app
from olumira.extensions import db
from test_account_recovery import email_link


def main():
    artifacts = ROOT / 'artifacts' / 'day16-accounts'
    artifacts.mkdir(parents=True, exist_ok=True)
    checks, failures = [], []
    stage = 'startup'
    with tempfile.TemporaryDirectory() as directory:
        app = create_app({'APP_ENV': 'testing', 'DATABASE': str(Path(directory) / 'browser.db'),
                          'AUTH_SETTINGS_LIMIT': '1000 per hour', 'AUTH_RECOVERY_IP_LIMIT': '1000 per hour',
                          'AUTH_RECOVERY_ACCOUNT_LIMIT': '1000 per hour'})
        with app.app_context():
            upgrade()
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        server = make_server('127.0.0.1', 0, app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        app.config['PUBLIC_APP_URL'] = origin
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                page.on('pageerror', lambda error: failures.append('JavaScript page error'))
                # A rejected token legitimately returns 410; other console failures are unexpected.
                page.on('console', lambda message: failures.append('Browser console error') if message.type == 'error' and '410' not in message.text else None)
                widths = [1440, 1280, 1024, 768, 390, 320]
                public = ['forgot-password', 'resend-verification', 'verify-email', 'reset-password', 'confirm-email']
                stage = 'responsive public recovery pages'
                for width in widths:
                    page.set_viewport_size({'width': width, 'height': 1000})
                    for route in public:
                        response = page.goto(origin + '/auth/' + route)
                        assert response.status == 200
                        assert page.locator('h1').count() == 1
                        if route == 'confirm-email':
                            assert page.get_by_role('link', name='Request a new change in account settings', exact=True).get_attribute('href') == '/auth/settings'
                        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                        page.screenshot(path=str(artifacts / f'{route}-{width}.png'), full_page=True)
                        checks.append(f'{route} at {width}px')
                page.set_viewport_size({'width': 1440, 'height': 1000})
                stage = 'registration and unverified account access'
                page.goto(origin + '/auth/register')
                page.locator('#display_name').fill('Fictional account review')
                page.locator('#email').fill('recovery-browser@example.com')
                page.locator('#password').fill('Fictional account passphrase 42')
                page.locator('#confirm_password').fill('Fictional account passphrase 42')
                page.locator('.auth-submit').click()
                assert page.url.endswith('/auth/check-email')
                page.goto(origin + '/auth/login')
                page.locator('#email').fill('recovery-browser@example.com')
                page.locator('#password').fill('Fictional account passphrase 42')
                page.locator('.auth-submit').click()
                assert page.url.endswith('/auth/verification')
                for width in widths:
                    page.set_viewport_size({'width': width, 'height': 1000})
                    page.goto(origin + '/auth/verification')
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    page.screenshot(path=str(artifacts / f'verification-{width}.png'), full_page=True)
                    checks.append(f'verification at {width}px')
                code, link, _ = email_link(app, 'verify_email')
                stage = 'no-JavaScript verification with emailed code'
                nojs = browser.new_context(java_script_enabled=False)
                fallback = nojs.new_page()
                fallback.goto(origin + '/auth/verify-email')
                fallback.locator('#recovery_code').fill(code)
                fallback.locator('.auth-submit').click()
                assert fallback.get_by_role('heading', name='Email verified', exact=True).is_visible()
                nojs.close()
                checks += ['unverified account gate', 'manual verification without JavaScript']
                stage = 'verified settings and responsive forms'
                page.goto(origin + '/auth/login')
                page.locator('#email').fill('recovery-browser@example.com')
                page.locator('#password').fill('Fictional account passphrase 42')
                page.locator('.auth-submit').click()
                for width in widths:
                    page.set_viewport_size({'width': width, 'height': 1000})
                    page.goto(origin + '/auth/settings')
                    assert page.locator('h1').count() == 1
                    assert page.get_by_text('Verified', exact=True).is_visible()
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    page.screenshot(path=str(artifacts / f'settings-{width}.png'), full_page=True)
                    checks.append(f'settings at {width}px')
                page.locator('#profile-display_name').fill('Updated fictional caregiver')
                page.get_by_role('button', name='Save display name', exact=True).click()
                assert page.get_by_role('status').is_visible()
                stage = 'pending email and confirmation'
                page.locator('#email-email').fill('updated-browser@example.com')
                page.locator('#email-current_password').fill('Fictional account passphrase 42')
                page.get_by_role('button', name='Verify new email', exact=True).click()
                assert page.get_by_text('Awaiting confirmation:', exact=False).is_visible()
                stage = 'opening email confirmation link'
                _, link, _ = email_link(app, 'change_email')
                page.goto(link)
                assert page.url.endswith('/auth/confirm-email')
                assert page.locator('[data-recovery-entry]').is_hidden()
                stage = 'submitting email confirmation'
                page.locator('.auth-submit').focus()
                page.keyboard.press('Enter')
                page.get_by_role('heading', name='Email updated', exact=True).wait_for(state='visible')
                assert page.get_by_role('heading', name='Email updated', exact=True).is_visible()
                checks += ['profile update', 'email remains pending until confirmation', 'fragment code removed from URL', 'keyboard email confirmation']
                stage = 'forgot password and reset'
                page.goto(origin + '/auth/forgot-password')
                page.locator('#email').fill('updated-browser@example.com')
                page.locator('.auth-submit').click()
                assert page.get_by_role('heading', name='Check your email', exact=True).is_visible()
                _, link, _ = email_link(app, 'reset_password')
                page.goto(link)
                assert page.url.endswith('/auth/reset-password')
                assert page.locator('[data-recovery-entry]').is_hidden()
                page.locator('#password').fill('Fictional recovered passphrase 84')
                page.locator('#confirm_password').fill('Fictional recovered passphrase 84')
                page.locator('.auth-submit').click()
                assert page.get_by_role('heading', name='Password reset', exact=True).is_visible()
                checks += ['generic forgot-password confirmation', 'password reset from encrypted test inbox']
                stage = 'new credentials, password settings, and session revocation'
                page.goto(origin + '/auth/login')
                page.locator('#email').fill('updated-browser@example.com')
                page.locator('#password').fill('Fictional recovered passphrase 84')
                page.locator('.auth-submit').click()
                page.goto(origin + '/auth/settings')
                page.locator('#password-current_password').fill('Fictional recovered passphrase 84')
                page.locator('#password-password').fill('Fictional final passphrase 126')
                page.locator('#password-confirm_password').fill('Fictional final passphrase 126')
                page.get_by_role('button', name='Update password', exact=True).click()
                assert page.url.endswith('/auth/login')
                checks += ['updated email sign-in', 'password-change settings', 'current session ended after password change']
                browser.close()
            assert not failures
        except Exception as error:
            failures.append('Failed stage: ' + stage + ' (' + type(error).__name__ + ')')
            try:
                failures.append('Page path: ' + urlsplit(page.url).path)
                for text in page.locator('.ui-alert-error, .auth-field-error').all_text_contents():
                    failures.append('Validation: ' + text)
            except Exception:
                pass
        finally:
            server.shutdown()
            thread.join()
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        report = dict(checks=checks, failures=failures)
        (artifacts / 'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        if failures:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
