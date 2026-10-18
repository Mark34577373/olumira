"""Security regressions use temporary databases and fictional accounts only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask_migrate import upgrade
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from olumira import create_app
from olumira.extensions import db
from olumira.models import User, Owner, Routine, Observation, AuthSession
from services.database import ensure_workspace, transaction
from services.authentication import (register_user, token_digest, revoke_all_sessions,
                                     PASSWORD_METHOD, authenticate)
from services.routines import get_routines
from services.observations import add_observation
from support import PASSWORD, csrf_token, post, create_user, login


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app({'APP_ENV': 'testing', 'DATABASE': str(Path(self.temp.name) / 'auth.db'),
                              'AUTH_LOGIN_IP_LIMIT': '1000 per minute', 'AUTH_LOGIN_ACCOUNT_LIMIT': '1000 per minute',
                              'AUTH_REGISTER_LIMIT': '1000 per hour'})
        with self.app.app_context():
            upgrade()
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp.cleanup()

    def registration(self, **changes):
        values = dict(display_name='Fictional caregiver', email='fictional@example.com',
                      password=PASSWORD, confirm_password=PASSWORD)
        values.update(changes)
        return post(self.client, '/auth/register', values)

    def test_registration_hash_and_no_automatic_login(self):
        self.assertEqual(self.registration(email=' FICTIONAL@Example.com ').status_code, 302)
        with self.app.app_context():
            user = db.session.scalar(select(User))
            self.assertEqual(user.email, 'fictional@example.com')
            self.assertFalse(user.email_verified)
            self.assertTrue(check_password_hash(user.password_hash, PASSWORD))
            self.assertTrue(user.password_hash.startswith(PASSWORD_METHOD + '$'))
            self.assertNotIn(PASSWORD, user.password_hash)
            self.assertIsNotNone(user.created_at)
            self.assertIsNotNone(user.updated_at)
            self.assertEqual(len(get_routines(user.owner_id)), 5)
            self.assertEqual(db.session.scalar(select(func.count()).select_from(AuthSession)), 0)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_validation_duplicate_email_and_passwords_never_echoed(self):
        cases = [dict(email='not-an-email'), dict(display_name='   '), dict(password='short'),
                 dict(password='x' * 129), dict(confirm_password='different'),
                 dict(password='passwordpassword', confirm_password='passwordpassword')]
        for values in cases:
            response = self.registration(**values)
            self.assertEqual(response.status_code, 422)
            self.assertIn('aria-invalid="true"', response.text)
            self.assertNotIn(PASSWORD, response.text)
        self.registration()
        self.assertEqual(self.registration(email='FICTIONAL@example.com').status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count()).select_from(User)), 1)
            self.assertEqual(db.session.scalar(select(func.count()).select_from(Owner)), 1)

    def test_registration_duplicate_response_does_not_disclose_membership(self):
        first = self.registration()
        duplicate = self.registration(email='FICTIONAL@example.com')
        self.assertEqual((first.status_code, first.location), (duplicate.status_code, duplicate.location))
        self.assertIn('/auth/check-email', duplicate.location)
        page = self.client.get(duplicate.location)
        self.assertNotIn('already exists', page.text)
        self.assertNotIn(PASSWORD, page.text)
        self.assertEqual(self.client.get('/').status_code, 302)
        from olumira.models import EmailOutbox
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count()).select_from(EmailOutbox)), 1)

    def test_database_email_uniqueness_and_normalization(self):
        create_user(self.app)
        with self.app.app_context():
            user = db.session.scalar(select(User))
            for index, email in enumerate(('fictional@example.com', 'UPPER@example.com')):
                owner_id = 'constraint-owner-' + str(index)
                with transaction() as store:
                    store.add(Owner(id=owner_id, created_at='2026-10-16'))
                with self.assertRaises(IntegrityError):
                    with transaction() as store:
                        store.add(User(id='duplicate-' + str(index), email=email, display_name='Test', password_hash='not-a-credential',
                                       email_verified=False, owner_id=owner_id))

    def test_login_rotates_session_and_password_hash_upgrade(self):
        user_id, owner = create_user(self.app)
        with self.client.session_transaction() as cookie:
            cookie['owner_id'] = 'legacy-untrusted-owner'
            cookie['pre_login_marker'] = 'must-disappear'
        before = csrf_token(self.client)
        login(self.client)
        after = csrf_token(self.client)
        self.assertNotEqual(before, after)
        with self.client.session_transaction() as cookie:
            self.assertNotIn('owner_id', cookie)
            self.assertNotIn('pre_login_marker', cookie)
            token = cookie['_auth_sid']
        with self.app.app_context():
            record = db.session.get(AuthSession, token_digest(token))
            self.assertEqual(record.user_id, user_id)
            self.assertNotEqual(record.token_hash, token)
            user = db.session.get(User, user_id)
            with transaction():
                user.password_hash = generate_password_hash(PASSWORD, method='scrypt:32768:8:1')
            authenticate(user.email, PASSWORD)
            self.assertTrue(user.password_hash.startswith(PASSWORD_METHOD + '$'))
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_wrong_and_unknown_credentials_use_same_message(self):
        create_user(self.app)
        responses = [post(self.client, '/auth/login', {'email': email, 'password': 'An incorrect long password'})
                     for email in ('fictional@example.com', 'unknown@example.com')]
        for response in responses:
            self.assertEqual(response.status_code, 401)
            self.assertIn('Email or password is incorrect.', response.text)
        with self.client.session_transaction() as cookie:
            self.assertNotIn('_auth_sid', cookie)

    def test_all_application_routes_protected(self):
        for path in ('/', '/routines', '/communication', '/observations', '/resources'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/auth/login', response.location)
        for path in ('/auth/login', '/auth/register', '/static/css/style.css'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_csrf_every_state_changing_endpoint(self):
        self.assertEqual(self.client.post('/auth/register').status_code, 400)
        self.assertEqual(self.client.post('/auth/login').status_code, 400)
        create_user(self.app)
        login(self.client)
        paths = ['/auth/logout', '/routines/add', '/routines/add-template', '/routines/1/toggle',
                 '/routines/1/edit', '/routines/1/delete', '/observations']
        for path in paths:
            self.assertEqual(self.client.post(path).status_code, 400, path)
            self.assertEqual(self.client.post(path, data={'csrf_token': 'forged'}).status_code, 400, path)
        other = self.app.test_client()
        self.assertEqual(self.client.post('/auth/logout', data={'csrf_token': csrf_token(other)}).status_code, 400)

    def test_logout_revokes_cookie_replay_and_requires_post(self):
        create_user(self.app)
        login(self.client)
        name = self.app.config['SESSION_COOKIE_NAME']
        copied_cookie = self.client.get_cookie(name).value
        self.assertEqual(self.client.get('/auth/logout').status_code, 405)
        response = post(self.client, '/auth/logout', follow_redirects=True)
        self.assertIn('signed out safely', response.text)
        self.assertEqual(self.client.get('/').status_code, 302)
        self.client.set_cookie(name, copied_cookie)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_absolute_and_idle_expiration_and_bulk_revocation(self):
        user_id, owner = create_user(self.app)
        for field in ('expires_at', 'last_seen_at'):
            login(self.client)
            with self.client.session_transaction() as cookie:
                digest = token_digest(cookie['_auth_sid'])
            with self.app.app_context(), transaction():
                record = db.session.get(AuthSession, digest)
                setattr(record, field, 1)
            response = self.client.get('/', follow_redirects=True)
            self.assertIn('Your session ended.', response.text)
            self.assertIn('Sign in to Olumira', response.text)
        login(self.client)
        other = self.app.test_client()
        login(other)
        with self.app.app_context():
            revoke_all_sessions(user_id)
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(other.get('/').status_code, 302)

    def test_forged_identity_without_server_session_rejected(self):
        user_id, owner = create_user(self.app)
        with self.client.session_transaction() as cookie:
            cookie['_user_id'] = user_id
            cookie['_auth_sid'] = 'x' * 43
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_open_redirect_prevention_and_valid_return_path(self):
        create_user(self.app)
        for destination in ('https://evil.example', '//evil.example', '/\\evil.example', '/%2f%2fevil.example',
                            '\r\nhttps://evil.example', '/auth/logout', '/routines?next=https://evil.example'):
            response = post(self.client, '/auth/login', {'email': 'fictional@example.com', 'password': PASSWORD, 'next': destination})
            self.assertEqual(response.location, '/')
            post(self.client, '/auth/logout')
        response = post(self.client, '/auth/login?next=/routines', {'email': 'fictional@example.com', 'password': PASSWORD})
        self.assertEqual(response.location, '/routines')

    def test_legacy_and_cross_account_access_blocked(self):
        with self.app.app_context():
            ensure_workspace('old-visitor')
            legacy_id = get_routines('old-visitor')[0]['id']
            add_observation('old-visitor', 'Legacy private test', '2026-10-16', 'Do not expose', '', '')
        first_id, first_owner = create_user(self.app)
        other_id, other_owner = create_user(self.app, 'second@example.com')
        with self.app.app_context():
            first_routine = get_routines(first_owner)[0]['id']
            add_observation(first_owner, 'First private test', '2026-10-16', 'Only first', '', '')
        login(self.client, 'second@example.com')
        with self.client.session_transaction() as cookie:
            cookie['owner_id'] = first_owner
        self.assertNotIn('First private test', self.client.get('/observations').text)
        self.assertNotIn('Legacy private test', self.client.get('/observations').text)
        for routine_id in (legacy_id, first_routine):
            for suffix, data in [('toggle', {}), ('delete', {}), ('edit', {'name': 'Attempt', 'category': 'General'})]:
                self.assertEqual(post(self.client, f'/routines/{routine_id}/{suffix}', data).status_code, 404)
        post(self.client, '/observations', {'activity': 'Second only', 'date': '2026-10-16'})
        with self.app.app_context():
            observation = db.session.scalar(select(Observation).where(Observation.activity == 'Second only'))
            self.assertEqual(observation.owner_id, other_owner)
            self.assertEqual(db.session.get(Routine, first_routine).name, 'Wake up')
        html = self.client.get('/communication/quick').text
        self.assertIn(f'data-storage-scope="{other_id}.{other_owner}.workspace"', html)
        self.assertNotIn(f'data-storage-scope="{first_id}"', html)

    def test_rate_limits_ip_account_and_registration(self):
        self.app.config.update(AUTH_LOGIN_IP_LIMIT='2 per minute', AUTH_LOGIN_ACCOUNT_LIMIT='100 per minute')
        for attempt in range(3):
            response = post(self.client, '/auth/login', {'email': 'missing@example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response.headers)
        self.app.config.update(AUTH_REGISTER_LIMIT='1 per hour')
        self.assertEqual(self.registration(email='first@example.com').status_code, 302)
        self.assertEqual(self.registration(email='second@example.com').status_code, 429)

    def test_account_limit_across_ip_addresses(self):
        self.app.config.update(AUTH_LOGIN_ACCOUNT_LIMIT='1 per minute')
        first = post(self.client, '/auth/login', {'email': 'MISSING@example.com', 'password': PASSWORD})
        second = post(self.client, '/auth/login', {'email': 'missing@example.com', 'password': PASSWORD}, environ_overrides={'REMOTE_ADDR': '192.0.2.1'})
        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 429)

    def test_cookie_security_and_private_page_headers(self):
        create_user(self.app)
        response = login(self.client)
        cookie = response.headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Lax', cookie)
        response = self.client.get('/')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')

    def test_sensitive_input_does_not_appear_in_error_logs(self):
        from sqlalchemy.exc import SQLAlchemyError
        with patch('olumira.routes.auth.register_user', side_effect=SQLAlchemyError('DO-NOT-LOG-PRIVATE-PAYLOAD')):
            with self.assertLogs(self.app.logger, level='ERROR') as captured:
                response = self.registration()
        self.assertEqual(response.status_code, 500)
        output = ''.join(captured.output)
        self.assertNotIn('DO-NOT-LOG-PRIVATE-PAYLOAD', output)
        self.assertNotIn(PASSWORD, output)
        self.assertNotIn('fictional@example.com', output)

    def test_session_handle_cannot_be_attached_to_another_identity(self):
        first, first_owner = create_user(self.app)
        second, second_owner = create_user(self.app, 'second@example.com')
        login(self.client)
        with self.client.session_transaction() as cookie:
            cookie['_user_id'] = second
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_duplicate_race_rolls_back_new_owner_and_starter_records(self):
        # Simulate a duplicate precheck racing with another successful registration.
        create_user(self.app)
        with self.app.app_context():
            actual_scalar = db.session.scalar
            calls = 0
            def raced_scalar(statement, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return None
                return actual_scalar(statement, *args, **kwargs)
            with patch.object(db.session, 'scalar', side_effect=raced_scalar):
                self.assertIsNone(register_user('fictional@example.com', 'Fictional duplicate', PASSWORD))
            self.assertEqual(db.session.scalar(select(func.count()).select_from(Owner)), 1)
            self.assertEqual(db.session.scalar(select(func.count()).select_from(Routine)), 5)
