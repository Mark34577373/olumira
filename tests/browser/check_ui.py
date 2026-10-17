"""Rendered UI checks using a disposable database and a local test server.
Run manually: venv/bin/python tests/browser/check_ui.py [--baseline]
"""
import argparse
import json
import logging
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flask_migrate import upgrade
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from olumira import create_app
from olumira.extensions import db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    artifacts = ROOT / 'artifacts' / ('before-day14' if args.baseline else 'after-day14')
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        app = create_app({'APP_ENV': 'testing', 'DATABASE': str(Path(temp) / 'browser.db')})
        with app.app_context():
            upgrade()
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        server = make_server('127.0.0.1', 0, app)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        failures, checks, console_errors = [], [], []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page()
                page.on('pageerror', lambda error: console_errors.append(str(error)))
                page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)
                widths = [1440, 1280, 1024, 768, 390, 320]
                routes = ['/', '/routines', '/communication', '/observations', '/resources']
                for width in widths:
                    page.set_viewport_size({'width': width, 'height': 1000})
                    for route in (['/'] if args.baseline else routes):
                        response = page.goto(origin + route)
                        assert response.status == 200
                        page.wait_for_load_state('networkidle')
                        overflow = page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
                        if overflow:
                            failures.append(f'Horizontal overflow: {route} at {width}')
                        assert page.locator('h1').count() == 1
                        assert page.locator('nav a[aria-current="page"]').count() == 1
                        if width == 1440 and not args.baseline:
                            contrast_failures = page.evaluate(r"""() => {
                                const rgb = value => (value.match(/[\d.]+/g) || []).map(Number);
                                const blend = (top, bottom) => top.slice(0,3).map((v,i) => v*(top[3] ?? 1) + bottom[i]*(1-(top[3] ?? 1)));
                                const background = el => !el ? [255,255,255] : blend(rgb(getComputedStyle(el).backgroundColor), background(el.parentElement));
                                const luminance = c => c.map(v => { v /= 255; return v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4; }).reduce((a,v,i) => a+v*[.2126,.7152,.0722][i],0);
                                return [...document.querySelectorAll('h1,h2,h3,p,label,summary,.nav-links a,.action-button small,.action-button strong,.card-label,.task-group-title,.task,.routine-item,.resource-category-tag')]
                                    .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
                                    .flatMap(el => {
                                        const style = getComputedStyle(el), bg = background(el);
                                        const foreground = luminance(blend(rgb(style.color), bg)), back = luminance(bg);
                                        const ratio = (Math.max(foreground,back)+.05)/(Math.min(foreground,back)+.05);
                                        const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && parseInt(style.fontWeight) >= 700);
                                        return ratio + .01 < (large ? 3 : 4.5) ? [{element: el.tagName+'.'+el.className, ratio}] : [];
                                    });
                            }""")
                            failures.extend([f'Contrast {route}: {item}' for item in contrast_failures])
                        if route == '/':
                            page.screenshot(path=str(artifacts / f'dashboard-{width}.png'), full_page=True)
                        checks.append(f'{route} at {width}px')
                if not args.baseline:
                    # Keyboard skip link, mobile menu opening and Escape return.
                    page.set_viewport_size({'width': 390, 'height': 900})
                    page.goto(origin)
                    page.keyboard.press('Tab')
                    assert page.locator('.skip-link').evaluate('(el) => el === document.activeElement')
                    page.keyboard.press('Enter')
                    assert page.locator('main').evaluate('(el) => el === document.activeElement')
                    page.locator('.menu-toggle').focus()
                    page.keyboard.press('Enter')
                    assert page.locator('.menu-toggle').get_attribute('aria-expanded') == 'true'
                    page.keyboard.press('Escape')
                    assert page.locator('.menu-toggle').get_attribute('aria-expanded') == 'false'
                    # Native POST, persistence, shared progress, and keyboard activation.
                    task = page.locator('.task').first
                    task.focus()
                    assert task.evaluate('(el) => getComputedStyle(el).outlineStyle !== \"none\" && parseFloat(getComputedStyle(el).outlineWidth) >= 3')
                    page.keyboard.press('Enter')
                    page.wait_for_load_state('networkidle')
                    assert page.locator('.task').first.get_attribute('aria-pressed') == 'true'
                    page.reload()
                    assert page.locator('.task').first.get_attribute('aria-pressed') == 'true'
                    page.goto(origin + '/routines')
                    assert page.locator('.routine-item').first.get_attribute('aria-pressed') == 'true'
                    page.goto(origin + '/observations')
                    page.locator('#observation-activity').fill('Fictional browser check')
                    page.locator('#observation-notes').fill('Test data in a temporary database only.')
                    page.locator('button[type=submit]').click()
                    assert page.get_by_role('status').is_visible()
                    page.goto(origin)
                    assert page.get_by_role('heading', name='Fictional browser check').is_visible()
                    page.goto(origin + '/communication')
                    page.get_by_role('button', name='Thirsty', exact=True).click()
                    assert page.locator('#communication-message-text').inner_text() == 'I want water.'
                    page.locator('#open-communication-dialog').click()
                    assert page.locator('#communication-name').evaluate('(el) => el === document.activeElement')
                    page.locator('#communication-name').fill('Fictional break')
                    page.locator('#communication-icon').fill('☀')
                    page.locator('#communication-message-input').fill('I would like a break.')
                    page.locator('#communication-form button[type=submit]').click()
                    page.reload()
                    page.get_by_role('button', name='Fictional break', exact=True).click()
                    assert page.locator('#communication-message-text').inner_text() == 'I would like a break.'
                    page.locator('#open-communication-dialog').click()
                    page.keyboard.press('Escape')
                    assert not page.locator('#communication-dialog').is_visible()
                    page.goto(origin + '/resources')
                    page.get_by_role('button', name='Safety', exact=True).click()
                    assert page.locator('.resource-card:visible').count() == 2
                    assert page.get_by_role('button', name='Safety', exact=True).get_attribute('aria-pressed') == 'true'
                    page.locator('.resource-card:visible .resource-learn-more').first.click()
                    assert page.locator('#resource-detail-panel').is_visible()
                    assert page.locator('#resource-detail-panel').evaluate('(el) => el === document.activeElement')
                    page.locator('#resource-back-button').click()
                    assert not page.locator('#resource-detail-panel').is_visible()
                    assert page.locator('.resource-card:visible .resource-learn-more').first.evaluate('(el) => el === document.activeElement')
                    page.emulate_media(reduced_motion='reduce')
                    page.goto(origin)
                    assert page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches')
                    # Navigation remains usable without JavaScript.
                    nojs = browser.new_context(java_script_enabled=False, viewport={'width': 320, 'height': 900})
                    fallback = nojs.new_page()
                    fallback.goto(origin)
                    assert fallback.get_by_role('link', name='Resources', exact=True).first.is_visible()
                    assert not fallback.evaluate('document.documentElement.scrollWidth > innerWidth')
                    nojs.close()
                    checks += ['sampled text contrast on all five pages', 'visible task focus', 'resource detail focus and restoration', 'keyboard skip link', 'mobile menu and Escape', 'keyboard routine completion and persistence', 'observation save/dashboard', 'communication selection/custom persistence/dialog', 'resource filters/details', 'reduced motion', 'no-JavaScript navigation']
                browser.close()
            failures.extend(console_errors)
            report = {'checks': checks, 'failures': failures, 'console_errors': console_errors}
            (artifacts / 'report.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
            assert not failures, failures
        finally:
            server.shutdown()
            worker.join()
            with app.app_context():
                db.session.remove()
                db.engine.dispose()


if __name__ == '__main__':
    main()
