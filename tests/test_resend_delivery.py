"""HTTPS transport and real migrated outbox/request integration; network is mocked."""
import json
import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import select
from test_account_recovery import RecoveryTests as _RecoveryFixture
from olumira.extensions import db
from olumira.models import EmailOutbox
from services.email_delivery import send_resend, message_for, deliver_pending


class ResendTests(unittest.TestCase):
    setUp = _RecoveryFixture.setUp
    tearDown = _RecoveryFixture.tearDown
    register = _RecoveryFixture.register

    def enable(self):
        self.app.config.update(MAIL_BACKEND='resend', RESEND_API_KEY='fictional-private-key',
                               MAIL_DELIVERY_MODE='request')

    def test_signup_sends_committed_message_and_does_not_repeat(self):
        self.enable()
        with patch('services.email_delivery.send_resend') as send:
            self.assertEqual(self.register().status_code, 302)
            self.assertEqual(send.call_count, 1)
            self.client.get('/auth/check-email')
            self.assertEqual(send.call_count, 1)
        with self.app.app_context():
            job = db.session.scalar(select(EmailOutbox))
            self.assertIsNotNone(job.delivered_at)
            self.assertEqual(job.attempts, 1)

    def test_failure_keeps_job_retryable_and_response_generic(self):
        self.enable()
        with patch('services.email_delivery.send_resend', side_effect=RuntimeError('private-key-token')):
            with self.assertLogs(self.app.logger, level='WARNING') as logs:
                self.assertEqual(self.register().status_code, 302)
        self.assertNotIn('private-key-token', '\n'.join(logs.output))
        with self.app.app_context():
            job = db.session.scalar(select(EmailOutbox))
            self.assertIsNone(job.delivered_at)
            self.assertEqual(job.last_error, 'delivery_failed')
            self.assertGreater(job.available_at, job.created_at)

    def test_resend_recovers_after_failure_without_sending_duplicate_signup(self):
        from support import post
        self.enable()
        with patch('services.email_delivery.send_resend', side_effect=RuntimeError('offline')):
            self.register()
        with patch('services.email_delivery.send_resend') as send:
            self.register()  # duplicate remains generic and creates no new job
            send.assert_not_called()
            result = post(self.client, '/auth/resend-verification', {'email': 'fictional@example.com'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(send.call_count, 1)
        with self.app.app_context():
            jobs = list(db.session.scalars(select(EmailOutbox)))
            self.assertEqual(len(jobs), 2)
            self.assertEqual(sum(job.delivered_at is not None for job in jobs), 1)
            self.assertEqual(sum(job.cancelled_at is not None for job in jobs), 1)

    def test_scope_and_expired_token_prevent_sending(self):
        self.register()  # default development mode only queues
        with self.app.app_context():
            self.enable()
            with patch('services.email_delivery.send_resend') as send:
                self.assertEqual(deliver_pending(job_ids=[])['sent'], 0)
                job = db.session.scalar(select(EmailOutbox))
                job.expires_at = 1
                db.session.commit()
                self.assertEqual(deliver_pending()['cancelled'], 1)
                send.assert_not_called()

    def test_https_payload_idempotency_and_provider_rejection(self):
        self.register()
        with self.app.app_context():
            self.enable()
            job = db.session.scalar(select(EmailOutbox))
            message = message_for(job)
            with patch('services.email_delivery.http.client.HTTPSConnection') as factory:
                response = factory.return_value.getresponse.return_value
                response.status = 200
                response.read.return_value = b'{"id":"fictional-provider-id"}'
                send_resend(message, job.id)
                self.assertEqual(factory.call_args.args[0], 'api.resend.com')
                self.assertTrue(factory.call_args.kwargs['context'].check_hostname)
                args = factory.return_value.request.call_args
                self.assertEqual(args.args, ('POST', '/emails'))
                self.assertEqual(args.kwargs['headers']['Idempotency-Key'], 'olumira-' + job.id)
                self.assertIn('#token=', json.loads(args.kwargs['body'])['text'])
                response.status = 403
                with self.assertRaisesRegex(RuntimeError, 'provider rejected'):
                    send_resend(message, job.id)
                self.assertEqual(factory.return_value.close.call_count, 2)

# Fixture reuse without collecting the source test class a second time.
del _RecoveryFixture

class ResendConfigurationTests(unittest.TestCase):
    def test_production_https_requires_key_and_keeps_security(self):
        from olumira.config import configuration
        from support import production_mail_settings
        settings = dict(APP_ENV='production', SECRET_KEY='fictional-secret-at-least-thirty-two-characters',
                        DATABASE_URL='postgresql://localhost/fictional?sslmode=verify-full',
                        RATELIMIT_STORAGE_URI='redis://localhost:6379/15',
                        **production_mail_settings())
        settings.update(MAIL_BACKEND='resend', MAIL_DELIVERY_MODE='request',
                        RESEND_API_KEY='fictional-key', SMTP_HOST='', SMTP_PASSWORD='', SMTP_USERNAME='')
        result = configuration(settings)
        self.assertTrue(result['SESSION_COOKIE_SECURE'])
        self.assertTrue(result['WTF_CSRF_ENABLED'])
        with self.assertRaises(ValueError):
            configuration(dict(settings, RESEND_API_KEY=''))
        with self.assertRaises(ValueError):
            configuration(dict(settings, MAIL_BACKEND='smtp'))
