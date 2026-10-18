"""Private expired-mail minimization with deterministic time and dry-run semantics."""

import unittest
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import EmailOutbox
from services.email_delivery import expired_payloads
import test_communication as fixture


class MailRetentionTests(unittest.TestCase):
    setUp = fixture.CommunicationTests.setUp
    tearDown = fixture.CommunicationTests.tearDown

    def test_only_expired_payloads_scrub_and_repeat_safely(self):
        moment = 2000000000
        with self.app.app_context():
            # Isolated fixture outbox only. Both values are synthetic encrypted-body stand-ins.
            for index, expiry in enumerate([moment - 1, moment + 600]):
                db.session.add(
                    EmailOutbox(
                        id=str(index) * 32,
                        user_id=self.uid,
                        kind="password_changed",
                        encrypted_payload="FICTIONAL-PRIVATE-PAYLOAD",
                        created_at=moment - 10,
                        available_at=moment,
                        expires_at=expiry,
                        attempts=0,
                    )
                )
            db.session.commit()
            self.assertEqual(expired_payloads(now=moment), 1)
            self.assertEqual(
                db.session.get(EmailOutbox, "0" * 32).encrypted_payload,
                "FICTIONAL-PRIVATE-PAYLOAD",
            )
            self.assertEqual(expired_payloads(now=moment, apply=True), 1)
            self.assertEqual(expired_payloads(now=moment, apply=True), 0)
            db.session.expire_all()
            self.assertEqual(
                db.session.get(EmailOutbox, "0" * 32).encrypted_payload, ""
            )
            self.assertEqual(
                db.session.get(EmailOutbox, "1" * 32).encrypted_payload,
                "FICTIONAL-PRIVATE-PAYLOAD",
            )
            self.assertIsNotNone(db.session.get(EmailOutbox, "0" * 32).created_at)
        dry = self.app.test_cli_runner().invoke(args=["mail-retention"])
        self.assertEqual(dry.exit_code, 0)
        self.assertIn("Would scrub", dry.output)
        self.assertNotIn("FICTIONAL-PRIVATE-PAYLOAD", dry.output)
