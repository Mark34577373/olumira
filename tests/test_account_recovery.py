"""Day 16 account lifecycle and delivery tests; no real email is sent."""
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from flask_migrate import upgrade
from sqlalchemy import select, func
from werkzeug.security import check_password_hash
from olumira import create_app
from olumira.extensions import db
from olumira.models import User, AuthSession, AccountToken, EmailOutbox
from services.database import transaction
from services.authentication import register_user, authenticate, start_session, token_digest
from services import account_recovery as accounts
from services.email_delivery import cipher, message_for, deliver_pending, send_smtp
from support import PASSWORD, post, create_user, login, production_mail_settings

NEW_PASSWORD = 'Fictional river garden passphrase 84'


def email_link(app, kind, user_id=None):
    with app.app_context():
        query = select(EmailOutbox).join(AccountToken, EmailOutbox.token_hash == AccountToken.token_hash).where(
            EmailOutbox.kind == kind, AccountToken.used_at.is_(None), EmailOutbox.cancelled_at.is_(None))
        if user_id:
            query = query.where(EmailOutbox.user_id == user_id)
        job = db.session.scalar(query.order_by(EmailOutbox.created_at.desc(), EmailOutbox.id.desc()))
        if job is None:
            raise AssertionError('Expected a queued account email')
        payload = json.loads(cipher().decrypt(job.encrypted_payload.encode()))
        code = re.search(r'#token=([A-Za-z0-9_-]{43})', payload['text']).group(1)
        link = re.search(r'https?://\S+#token=[A-Za-z0-9_-]{43}', payload['text']).group(0)
        return code, link, job.id


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app({'APP_ENV': 'testing', 'DATABASE': str(Path(self.temp.name) / 'accounts.db'),
                              'AUTH_LOGIN_IP_LIMIT': '1000 per hour', 'AUTH_LOGIN_ACCOUNT_LIMIT': '1000 per hour',
                              'AUTH_REGISTER_LIMIT': '1000 per hour', 'AUTH_RECOVERY_IP_LIMIT': '1000 per hour',
                              'AUTH_RECOVERY_ACCOUNT_LIMIT': '1000 per hour', 'AUTH_SETTINGS_LIMIT': '1000 per hour',
                              'AUTH_TOKEN_LIMIT': '1000 per hour', 'PUBLIC_APP_URL': 'https://canonical.example.com'})
        with self.app.app_context():
            upgrade()
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp.cleanup()

    def register(self):
        return post(self.client, '/auth/register', dict(email='fictional@example.com', display_name='Fictional',
                                                      password=PASSWORD, confirm_password=PASSWORD))

    def request_reset(self, email='fictional@example.com'):
        return post(self.client, '/auth/forgot-password', {'email': email})

    def reset(self, code):
        return post(self.client, '/auth/reset-password', {'recovery_code': code, 'password': NEW_PASSWORD,
                                                         'confirm_password': NEW_PASSWORD})

    def settings(self, action, fields):
        return post(self.client, '/auth/settings', {'action': action, **fields})

    def test_registration_verification_gate_and_single_use(self):
        response = self.register()
        self.assertEqual(response.location, '/auth/check-email')
        code, link, job_id = email_link(self.app, 'verify_email')
        self.assertTrue(link.startswith('https://canonical.example.com/auth/verify-email#token='))
        with self.app.app_context():
            token = db.session.get(AccountToken, token_digest(code))
            job = db.session.get(EmailOutbox, job_id)
            self.assertEqual(token.purpose, 'verify_email')
            self.assertEqual(token.expires_at - token.created_at, 3600)
            self.assertNotIn(code, job.encrypted_payload)
            self.assertIsNone(db.session.get(AccountToken, code))
        response = login(self.client)
        self.assertEqual(response.location, '/auth/verification')
        for path in ('/', '/routines', '/communication', '/observations', '/resources'):
            self.assertEqual(self.client.get(path).location, '/auth/verification')
        self.assertEqual(self.client.get('/auth/settings').status_code, 200)
        # Opening a link does not consume it (email scanners and GET requests are safe).
        self.client.get('/auth/verify-email')
        with self.app.app_context():
            self.assertIsNone(db.session.get(AccountToken, token_digest(code)).used_at)
        response = post(self.client, '/auth/verify-email', {'recovery_code': code})
        self.assertIn('Email verified', response.text)
        self.assertEqual(post(self.client, '/auth/verify-email', {'recovery_code': code}).status_code, 410)
        self.assertEqual(self.client.get('/').status_code, 302)
        login(self.client)
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_expired_verification_resend_and_wrong_purpose(self):
        self.register()
        old, _, old_job = email_link(self.app, 'verify_email')
        with self.app.app_context(), transaction():
            db.session.get(AccountToken, token_digest(old)).expires_at = 1
        self.assertEqual(post(self.client, '/auth/verify-email', {'recovery_code': old}).status_code, 410)
        response = post(self.client, '/auth/resend-verification', {'email': 'FICTIONAL@example.com'})
        self.assertEqual(response.status_code, 200)
        fresh, _, _ = email_link(self.app, 'verify_email')
        self.assertNotEqual(old, fresh)
        self.assertEqual(self.reset(fresh).status_code, 410)
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(EmailOutbox, old_job).cancelled_at)
            self.assertIsNone(db.session.get(AccountToken, token_digest(fresh)).used_at)
        self.assertEqual(post(self.client, '/auth/verify-email', {'recovery_code': fresh}).status_code, 200)

    def test_recovery_responses_are_generic_and_not_smtp_dependent(self):
        create_user(self.app)
        with patch('services.email_delivery.send_smtp', side_effect=RuntimeError('Must not run in HTTP request')) as sender:
            known = self.request_reset()
            unknown = self.request_reset('unknown@example.com')
            for response in (known, unknown):
                self.assertEqual(response.status_code, 200)
                self.assertIn('If an account needs this email', response.text)
            self.assertEqual(known.text, unknown.text)
            sender.assert_not_called()
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count()).select_from(EmailOutbox)), 1)
        with patch('services.account_recovery.queue_email', side_effect=RuntimeError('private transport payload')):
            with self.assertLogs(self.app.logger, level='WARNING') as logs:
                response = self.request_reset()
            self.assertEqual(response.status_code, 200)
            self.assertIn('If an account needs this email', response.text)
            self.assertNotIn('private transport payload', ''.join(logs.output))

    def test_valid_reset_revokes_every_session_and_queues_notification(self):
        user_id, owner = create_user(self.app)
        login(self.client)
        other = self.app.test_client()
        login(other)
        self.request_reset()
        code, _, _ = email_link(self.app, 'reset_password')
        response = self.reset(code)
        self.assertIn('Password reset', response.text)
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(other.get('/').status_code, 302)
        self.assertEqual(self.reset(code).status_code, 410)
        with self.app.app_context():
            user = db.session.get(User, user_id)
            self.assertTrue(check_password_hash(user.password_hash, NEW_PASSWORD))
            self.assertTrue(user.email_verified)
            self.assertEqual(user.auth_version, 1)
            jobs = db.session.scalars(select(EmailOutbox).where(EmailOutbox.kind == 'password_changed')).all()
            self.assertEqual(len(jobs), 1)
            message = message_for(jobs[0])
            self.assertEqual(message.get_content_type(), 'multipart/alternative')
            self.assertNotIn(NEW_PASSWORD, message.as_string())
            self.assertIsNone(authenticate('fictional@example.com', PASSWORD))
            self.assertIsNotNone(authenticate('fictional@example.com', NEW_PASSWORD))

    def test_expired_invalid_replaced_and_malformed_reset_tokens(self):
        create_user(self.app)
        self.request_reset()
        old, _, _ = email_link(self.app, 'reset_password')
        self.request_reset()
        current, _, _ = email_link(self.app, 'reset_password')
        self.assertEqual(self.reset(old).status_code, 410)
        with self.app.app_context(), transaction():
            db.session.get(AccountToken, token_digest(current)).expires_at = 1
        self.assertEqual(self.reset(current).status_code, 410)
        self.assertEqual(self.reset('x' * 43).status_code, 410)
        self.assertEqual(self.reset('short').status_code, 422)
        with self.app.app_context():
            user = db.session.scalar(select(User))
            self.assertTrue(check_password_hash(user.password_hash, PASSWORD))

    def test_reset_does_not_verify_email_or_authenticate_the_user(self):
        self.register()
        self.request_reset()
        code, _, _ = email_link(self.app, 'reset_password')
        self.reset(code)
        with self.app.app_context():
            self.assertFalse(db.session.scalar(select(User)).email_verified)
            self.assertEqual(db.session.scalar(select(func.count()).select_from(AuthSession)), 0)

    def test_password_validation_does_not_consume_reset_token(self):
        create_user(self.app)
        self.request_reset()
        code, _, _ = email_link(self.app, 'reset_password')
        response = post(self.client, '/auth/reset-password', {'recovery_code': code, 'password': 'short', 'confirm_password': 'different'})
        self.assertEqual(response.status_code, 422)
        with self.app.app_context():
            self.assertIsNone(db.session.get(AccountToken, token_digest(code)).used_at)
        self.assertEqual(self.reset(code).status_code, 200)

    def test_settings_profile_authorization_and_sensitive_reauthentication(self):
        user_id, owner = create_user(self.app)
        other_id, other_owner = create_user(self.app, 'second@example.com')
        login(self.client)
        response = self.settings('profile', {'profile-display_name': 'Updated fictional name', 'user_id': other_id})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.get(User, user_id).display_name, 'Updated fictional name')
            self.assertNotEqual(db.session.get(User, other_id).display_name, 'Updated fictional name')
        response = self.settings('password', {'password-current_password': 'wrong', 'password-password': NEW_PASSWORD,
                                              'password-confirm_password': NEW_PASSWORD})
        self.assertEqual(response.status_code, 422)
        response = self.settings('email', {'email-current_password': 'wrong', 'email-email': 'new@example.com'})
        self.assertEqual(response.status_code, 422)
        with self.app.app_context():
            self.assertIsNone(db.session.get(User, user_id).pending_email)
        self.assertEqual(self.app.test_client().get('/auth/settings').status_code, 302)

    def test_password_change_revokes_sessions_tokens_and_notifies(self):
        user_id, owner = create_user(self.app)
        login(self.client)
        other = self.app.test_client()
        login(other)
        self.request_reset()
        code, _, _ = email_link(self.app, 'reset_password')
        response = self.settings('password', {'password-current_password': PASSWORD, 'password-password': NEW_PASSWORD,
                                              'password-confirm_password': NEW_PASSWORD})
        self.assertEqual(response.location, '/auth/login')
        self.assertEqual(other.get('/').status_code, 302)
        self.assertEqual(self.reset(code).status_code, 410)
        with self.app.app_context():
            self.assertTrue(check_password_hash(db.session.get(User, user_id).password_hash, NEW_PASSWORD))
            self.assertIsNotNone(db.session.scalar(select(EmailOutbox).where(EmailOutbox.kind == 'password_changed')))

    def test_email_change_only_activates_after_confirmation(self):
        user_id, owner = create_user(self.app)
        login(self.client)
        other = self.app.test_client()
        login(other)
        response = self.settings('email', {'email-current_password': PASSWORD, 'email-email': 'NEW@example.com'})
        self.assertEqual(response.status_code, 302)
        code, _, _ = email_link(self.app, 'change_email')
        with self.app.app_context():
            user = db.session.get(User, user_id)
            self.assertEqual(user.email, 'fictional@example.com')
            self.assertEqual(user.pending_email, 'new@example.com')
        self.assertEqual(post(self.client, '/auth/verify-email', {'recovery_code': code}).status_code, 410)
        response = post(self.client, '/auth/confirm-email', {'recovery_code': code})
        self.assertIn('Email updated', response.text)
        self.assertEqual(other.get('/').status_code, 302)
        self.assertEqual(post(self.client, '/auth/confirm-email', {'recovery_code': code}).status_code, 410)
        with self.app.app_context():
            user = db.session.get(User, user_id)
            self.assertEqual(user.email, 'new@example.com')
            self.assertTrue(user.email_verified)
            self.assertIsNone(user.pending_email)
            self.assertEqual(len(db.session.scalars(select(EmailOutbox).where(EmailOutbox.kind == 'email_changed')).all()), 2)

    def test_email_change_duplicate_expiration_and_cancellation(self):
        user_id, owner = create_user(self.app)
        create_user(self.app, 'taken@example.com')
        login(self.client)
        self.assertEqual(self.settings('email', {'email-current_password': PASSWORD, 'email-email': 'taken@example.com'}).status_code, 422)
        self.settings('email', {'email-current_password': PASSWORD, 'email-email': 'new@example.com'})
        code, _, _ = email_link(self.app, 'change_email')
        with self.app.app_context(), transaction():
            db.session.get(AccountToken, token_digest(code)).expires_at = 1
        self.assertEqual(post(self.client, '/auth/confirm-email', {'recovery_code': code}).status_code, 410)
        self.settings('email', {'email-current_password': PASSWORD, 'email-email': 'new@example.com'})
        code, _, _ = email_link(self.app, 'change_email')
        self.assertEqual(self.settings('cancel', {'cancel-current_password': PASSWORD}).status_code, 302)
        self.assertEqual(post(self.client, '/auth/confirm-email', {'recovery_code': code}).status_code, 410)
        with self.app.app_context():
            self.assertEqual(db.session.get(User, user_id).email, 'fictional@example.com')

    def test_credential_generation_closes_login_reset_race(self):
        user_id, owner = create_user(self.app)
        with self.app.test_request_context('/auth/login'):
            user = authenticate('fictional@example.com', PASSWORD)
            self.assertIsNotNone(user)
            self.assertTrue(accounts.change_password(user_id, PASSWORD, NEW_PASSWORD))
            self.assertFalse(start_session(user))
        with self.app.app_context():
            self.assertEqual(db.session.scalar(select(func.count()).select_from(AuthSession)), 0)

    def test_sign_out_everywhere_requires_password_and_revokes_all(self):
        create_user(self.app)
        login(self.client)
        other = self.app.test_client()
        login(other)
        self.assertEqual(self.settings('sessions', {'sessions-current_password': 'wrong'}).status_code, 422)
        self.assertEqual(self.settings('sessions', {'sessions-current_password': PASSWORD}).location, '/auth/login')
        self.assertEqual(other.get('/').status_code, 302)

    def test_new_endpoints_enforce_csrf_and_resend_rate_limits(self):
        for path in ('/auth/verify-email', '/auth/forgot-password', '/auth/reset-password', '/auth/resend-verification', '/auth/confirm-email', '/auth/settings'):
            self.assertEqual(self.client.post(path).status_code, 400)
        self.app.config.update(AUTH_RECOVERY_ACCOUNT_LIMIT='1 per hour')
        first = post(self.client, '/auth/resend-verification', {'email': 'unknown@example.com'})
        second = post(self.client, '/auth/resend-verification', {'email': 'UNKNOWN@example.com'}, environ_overrides={'REMOTE_ADDR': '192.0.2.2'})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_canonical_links_and_encrypted_private_preview(self):
        html = self.client.get('/auth/register', base_url='http://untrusted.example').text
        csrf_value = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
        response = self.client.post('/auth/register', base_url='http://untrusted.example',
            data=dict(email='fictional@example.com', display_name='Fictional', password=PASSWORD,
                      confirm_password=PASSWORD, csrf_token=csrf_value))
        self.assertEqual(response.status_code, 302)
        code, link, job_id = email_link(self.app, 'verify_email')
        self.assertIn('canonical.example.com', link)
        self.assertNotIn('untrusted.example', link)
        output = Path(self.temp.name) / 'private.eml'
        result = self.app.test_cli_runner().invoke(args=['mail-preview', '--output', str(output), '--message-id', job_id])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(code, result.output)
        self.assertNotIn('fictional@example.com', result.output)
        self.assertNotEqual(self.app.test_cli_runner().invoke(args=['mail-preview', '--output', str(output)]).exit_code, 0)

    def test_mail_retry_failure_redacts_and_then_delivers(self):
        self.register()
        code, _, job_id = email_link(self.app, 'verify_email')
        with self.app.app_context():
            self.app.config['MAIL_BACKEND'] = 'smtp'
            with patch('services.email_delivery.send_smtp', side_effect=RuntimeError('private-token-' + code)):
                with self.assertLogs(self.app.logger, level='WARNING') as captured:
                    counts = deliver_pending()
            self.assertEqual(counts['failed'], 1)
            self.assertNotIn(code, ''.join(captured.output))
            job = db.session.get(EmailOutbox, job_id)
            self.assertEqual(job.last_error, 'delivery_failed')
            with transaction():
                job.available_at = 0
            with patch('services.email_delivery.send_smtp') as sender:
                self.assertEqual(deliver_pending()['sent'], 1)
                sender.assert_called_once()
            self.assertIsNotNone(db.session.get(EmailOutbox, job_id).delivered_at)
            with patch('services.email_delivery.send_smtp') as sender:
                self.assertEqual(deliver_pending()['sent'], 0)
                sender.assert_not_called()

    def test_expired_email_is_not_sent_and_smtp_uses_tls(self):
        self.register()
        code, _, job_id = email_link(self.app, 'verify_email')
        with self.app.app_context():
            self.app.config['MAIL_BACKEND'] = 'smtp'
            with transaction():
                db.session.get(EmailOutbox, job_id).expires_at = 1
            with patch('services.email_delivery.send_smtp') as sender:
                self.assertEqual(deliver_pending()['cancelled'], 1)
                sender.assert_not_called()
            self.app.config.update(SMTP_HOST='smtp.example.com', SMTP_USERNAME='fictional', SMTP_PASSWORD='fictional')
            with patch('smtplib.SMTP') as smtp:
                transport = smtp.return_value.__enter__.return_value
                transport.send_message.return_value = {}
                send_smtp(message_for(db.session.get(EmailOutbox, job_id)))
                transport.starttls.assert_called_once()
                transport.login.assert_called_once()

    def test_account_scoped_settings_throttle_and_stale_generation_rejection(self):
        user_id, owner = create_user(self.app)
        login(self.client)
        self.app.config['AUTH_SETTINGS_LIMIT'] = '1 per hour'
        self.assertEqual(self.settings('profile', {'profile-display_name': 'Fictional update'}).status_code, 302)
        response = post(self.client, '/auth/settings', {'action': 'profile', 'profile-display_name': 'Fictional second update'},
                        environ_overrides={'REMOTE_ADDR': '192.0.2.22'})
        self.assertEqual(response.status_code, 429)
        with self.app.app_context(), transaction():
            db.session.get(User, user_id).auth_version += 1
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_email_target_taken_after_request_and_purpose_binding(self):
        user_id, owner = create_user(self.app)
        login(self.client)
        self.settings('email', {'email-current_password': PASSWORD, 'email-email': 'later-taken@example.com'})
        code, _, _ = email_link(self.app, 'change_email')
        create_user(self.app, 'later-taken@example.com')
        self.assertEqual(post(self.client, '/auth/confirm-email', {'recovery_code': code}).status_code, 410)
        with self.app.app_context():
            self.assertEqual(db.session.get(User, user_id).email, 'fictional@example.com')

    def test_configuration_rejects_insecure_email_and_test_mode_never_sends(self):
        base = dict(APP_ENV='production', SECRET_KEY='fictional-configuration-secret-with-sufficient-length',
                    DATABASE_URL='postgresql://localhost/fictional', RATELIMIT_STORAGE_URI='redis://localhost:6379/15',
                    **production_mail_settings())
        for changes in (dict(PUBLIC_APP_URL='http://insecure.example.com'), dict(MAIL_ENCRYPTION_KEY=None),
                        dict(SMTP_PASSWORD=''), dict(MAIL_BACKEND='development'), dict(SMTP_SECURITY='plain')):
            with self.assertRaises(ValueError):
                create_app(dict(base, **changes))
        testing = create_app({'APP_ENV': 'testing', 'MAIL_BACKEND': 'smtp'})
        self.assertEqual(testing.config['MAIL_BACKEND'], 'development')
