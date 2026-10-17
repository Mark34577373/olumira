import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.exceptions import InternalServerError
from olumira import create_app
from flask_migrate import upgrade
from support import post, create_user, login, PASSWORD, production_mail_settings


class ArchitectureTests(unittest.TestCase):
    def test_factory_and_blueprints(self):
        app = create_app({'APP_ENV': 'testing'})
        self.assertEqual(set(app.blueprints), {'dashboard', 'routines', 'communication', 'observations', 'resources', 'auth', 'workspaces', 'care', 'calendar', 'onboarding'})
        self.assertFalse(app.debug)

    def test_production_configuration_fails_closed(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                create_app({'APP_ENV': 'production'})
            with self.assertRaises(ValueError):
                create_app({'APP_ENV': 'production', 'SECRET_KEY': 'test-only'})

    def test_error_pages_and_allow_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app({'APP_ENV': 'testing', 'DATABASE': str(Path(tmp) / 'test.db')})
            with app.app_context():
                upgrade()
            client = app.test_client()
            create_user(app)
            login(client)
            for path, method, code in [('/missing', 'get', 404), ('/routines/add', 'get', 405), ('/routines/add-template', 'post', 400)]:
                response = post(client, path) if method == 'post' else client.get(path)
                self.assertEqual(response.status_code, code)
                self.assertIn('Return to your dashboard', response.text)
                if code == 405:
                    self.assertIn('POST', response.headers['Allow'])
            with app.test_request_context('/'):
                response = app.handle_http_exception(InternalServerError())
                self.assertEqual(response.status_code, 500)
                self.assertNotIn('Traceback', response.get_data(as_text=True))

    def test_production_positive_settings_without_connecting(self):
        app = create_app({'APP_ENV': 'production', 'SECRET_KEY': 'fictional-test-key-that-is-not-used-in-production',
                          'DATABASE_URL': 'postgresql://localhost/olumira_test', 'RATELIMIT_STORAGE_URI': 'redis://localhost:6379/15', 'DEBUG': True, **production_mail_settings()})
        self.assertFalse(app.debug)
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
        self.assertTrue(app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql+psycopg://'))

    def test_database_errors_are_sanitized(self):
        from sqlalchemy.exc import SQLAlchemyError
        app = create_app({'APP_ENV': 'testing'})
        with patch('olumira.routes.auth.register_user', side_effect=SQLAlchemyError('fictional-sensitive-value')):
            with self.assertLogs(app.logger, level='ERROR') as captured:
                response = post(app.test_client(), '/auth/register', {'display_name': 'Fictional', 'email': 'fictional@example.com', 'password': PASSWORD, 'confirm_password': PASSWORD})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('fictional-sensitive-value', response.text)
        self.assertNotIn('fictional-sensitive-value', ''.join(captured.output))

    def test_postgres_baseline_compiles_offline(self):
        import io
        from contextlib import redirect_stdout
        app = create_app({'APP_ENV': 'testing', 'DATABASE_URL': 'postgresql+psycopg://localhost/olumira_test'})
        output = io.StringIO()
        with app.app_context(), redirect_stdout(output):
            upgrade(sql=True)
        sql = output.getvalue()
        self.assertIn('CREATE TABLE routine_completions', sql)
        self.assertIn('ON DELETE CASCADE', sql)
        self.assertIn('SERIAL', sql)

    def test_production_rejects_memory_limits_and_forces_secure_controls(self):
        settings = dict(APP_ENV='production', SECRET_KEY='fictional-secret-for-configuration-test-only',
                        DATABASE_URL='postgresql://localhost/olumira_test', **production_mail_settings())
        with self.assertRaises(ValueError):
            create_app(dict(settings, RATELIMIT_STORAGE_URI='memory://'))
        app = create_app(dict(settings, RATELIMIT_STORAGE_URI='redis://localhost:6379/15',
                              SESSION_COOKIE_HTTPONLY=False, SESSION_COOKIE_SECURE=False,
                              WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False))
        for setting in ('SESSION_COOKIE_HTTPONLY', 'SESSION_COOKIE_SECURE', 'WTF_CSRF_ENABLED', 'RATELIMIT_ENABLED'):
            self.assertTrue(app.config[setting])
        self.assertEqual(app.config['SESSION_COOKIE_NAME'], '__Host-olumira_session')
