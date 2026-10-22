"""Render-like HTTP upstream, real CSRF/login, and bounded redirect chains."""
import re
from unittest.mock import patch

import pytest
from flask_migrate import upgrade

from olumira import create_app
from olumira.config import configuration
from olumira.extensions import db
from olumira.models import WorkspaceMembership, User
from support import PASSWORD, create_user, production_mail_settings

ORIGIN = 'http://olumira.onrender.com'
FORWARDED = {'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '203.0.113.10'}


@pytest.fixture
def app():
    # Isolated DB/mail/limiter; enable the actual production transport handler
    # after migrations. No external production credentials/services are used.
    app = create_app(dict(APP_ENV='testing', TRUSTED_PROXY_HOPS=1,
                          PUBLIC_APP_URL='https://olumira.onrender.com',
                          TRUSTED_HOSTS=['olumira.onrender.com']))
    with app.app_context():
        upgrade()
    create_user(app)
    app.config.update(APP_ENV='production', SESSION_COOKIE_SECURE=True,
                      SESSION_COOKIE_NAME='__Host-olumira_session')
    return app


def get(client, path, **kwargs):
    return client.get(path, base_url=ORIGIN, headers=FORWARDED, **kwargs)


def sign_in(client):
    response = get(client, '/auth/login')
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text)[1]
    return client.post('/auth/login', base_url=ORIGIN,
                       headers={**FORWARDED, 'Referer': 'https://olumira.onrender.com/auth/login'},
                       data=dict(email='fictional@example.com', password=PASSWORD, csrf_token=token),
                       follow_redirects=True)


def test_render_requires_explicit_proxy_trust():
    settings = dict(APP_ENV='production', SECRET_KEY='fictional-production-key-long-enough',
                    DATABASE_URL='postgresql://localhost/fictional?sslmode=verify-full',
                    RATELIMIT_STORAGE_URI='redis://localhost:6379/15',
                    **production_mail_settings())
    with patch.dict('os.environ', {'RENDER': 'true', 'RENDER_SERVICE_TYPE': 'web', 'TRUSTED_PROXY_HOPS': '0'}):
        with pytest.raises(ValueError, match='TRUSTED_PROXY_HOPS=1'):
            configuration(settings)
        values = configuration(dict(settings, TRUSTED_PROXY_HOPS=1))
        assert values['SESSION_COOKIE_SECURE'] and values['WTF_CSRF_ENABLED']
    with patch.dict('os.environ', {'RENDER': '', 'TRUSTED_PROXY_HOPS': '0'}):
        assert configuration(settings)['TRUSTED_PROXY_HOPS'] == 0
    with patch.dict('os.environ', {'RENDER': 'true', 'RENDER_SERVICE_TYPE': 'cron', 'TRUSTED_PROXY_HOPS': '0'}):
        assert configuration(settings)['TRUSTED_PROXY_HOPS'] == 0


def test_public_and_auth_requests_terminate_behind_proxy(app):
    client = app.test_client()
    for path in ('/', '/features', '/auth/login', '/auth/register'):
        response = get(client, path, follow_redirects=True)
        assert response.status_code == 200
        assert not response.history
    for path in ('/dashboard', '/setup', '/workspaces'):
        response = get(client, path, follow_redirects=True)
        assert response.status_code == 200
        assert len(response.history) == 1
        assert response.request.path == '/auth/login'


def test_authenticated_setup_dashboard_and_workspace_have_no_cycle(app):
    client = app.test_client()
    response = sign_in(client)
    assert response.status_code == 200 and response.request.path == '/setup'
    assert len(response.history) == 1
    assert any('Secure;' in r.headers.get('Set-Cookie', '') for r in response.history)
    for path in ('/dashboard', '/setup', '/workspaces'):
        response = get(client, path, follow_redirects=True)
        assert response.status_code == 200 and not response.history
    with app.app_context():
        db.session.query(WorkspaceMembership).delete()
        db.session.commit()
    response = get(client, '/dashboard', follow_redirects=True)
    assert response.status_code == 200 and response.request.path == '/workspaces'
    assert len(response.history) == 1
    response = get(client, '/auth/login', follow_redirects=True)
    assert response.status_code == 200 and response.request.path == '/workspaces'
    assert len(response.history) == 1


def test_unverified_account_redirect_terminates(app):
    with app.app_context():
        db.session.query(User).update({'email_verified': False})
        db.session.commit()
    response = sign_in(app.test_client())
    assert response.status_code == 200 and response.request.path == '/auth/verification'
    assert len(response.history) == 1


def test_transport_canonical_redirect_and_untrusted_headers(app):
    client = app.test_client()
    for headers in ({}, {'X-Forwarded-Proto': 'http'}, {'X-Forwarded-Proto': 'https, http'}):
        response = client.get('/features?view=example', base_url=ORIGIN, headers=headers)
        assert response.status_code == 308
        assert response.location == 'https://olumira.onrender.com/features?view=example'
    # The trusted last proxy value wins; supplied host/port/prefix never do.
    response = client.get('/features', base_url=ORIGIN, headers={
        **FORWARDED, 'X-Forwarded-Proto': 'http, https',
        'X-Forwarded-Host': 'attacker.invalid', 'X-Forwarded-Port': '81',
        'X-Forwarded-Prefix': '/attacker'})
    assert response.status_code == 200
    assert client.get('/', base_url='http://attacker.invalid', headers=FORWARDED).status_code == 400
    assert client.post('/auth/login', base_url=ORIGIN).status_code == 400
    assert client.post('/auth/login', base_url=ORIGIN, headers=FORWARDED).status_code == 400  # CSRF
    assert client.get('/health/live', base_url=ORIGIN).status_code == 200


def test_zero_hops_reproduces_same_https_redirect_without_trusting_header():
    app = create_app(dict(APP_ENV='testing', TRUSTED_PROXY_HOPS=0,
                          PUBLIC_APP_URL='https://olumira.onrender.com'))
    app.config['APP_ENV'] = 'production'
    response = get(app.test_client(), '/')
    assert response.status_code == 308
    assert response.location == 'https://olumira.onrender.com/'
