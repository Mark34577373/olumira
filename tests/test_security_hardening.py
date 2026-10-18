"""Regression evidence for the Days 41–42 audit findings; fictional data only."""

import io
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olumira import create_app
from olumira.config import configuration, ROOT
from olumira.privacy_logging import (
    AccessPathFilter,
    configure_access_logging,
    security_event,
)
from support import production_mail_settings


class SecurityHardeningTests(unittest.TestCase):
    def test_testing_defaults_cannot_reuse_normal_database_or_external_services(self):
        poisoned = dict(
            DATABASE_URL="postgresql://private.invalid/real?sslmode=verify-full",
            RATELIMIT_STORAGE_URI="redis://private.invalid:6379/0",
            MAIL_BACKEND="smtp",
            SMTP_PASSWORD="DO-NOT-USE",
            MAIL_ENCRYPTION_KEY="invalid",
            PUBLIC_APP_URL="https://private.invalid",
        )
        with patch.dict("os.environ", poisoned):
            first = create_app({"APP_ENV": "testing"})
            second = create_app({"APP_ENV": "testing"})
        self.assertTrue(first.testing)
        self.assertEqual(first.config["SQLALCHEMY_DATABASE_URI"], "sqlite:///:memory:")
        self.assertEqual(first.config["MAIL_BACKEND"], "development")
        self.assertEqual(first.config["RATELIMIT_STORAGE_URI"], "memory://")
        self.assertNotEqual(first.secret_key, second.secret_key)
        for values in [
            dict(DATABASE=str(ROOT / "database/olumira.db")),
            dict(DATABASE_URL="sqlite:///" + str(ROOT / "database/olumira.db")),
        ]:
            with self.assertRaisesRegex(ValueError, "normal application database"):
                configuration(dict(APP_ENV="testing", **values))

    def test_production_host_transport_headers_and_proxy_are_explicit(self):
        values = dict(
            APP_ENV="production",
            SECRET_KEY="fictional-production-config-key-not-a-real-secret",
            DATABASE_URL="postgresql://localhost/fictional?sslmode=verify-full",
            RATELIMIT_STORAGE_URI="redis://localhost:6379/15",
            **production_mail_settings()
        )
        app = create_app(values)

        # Routing-only fixture deliberately performs no DB, SMTP or Redis I/O.
        @app.get("/transport-check")
        def probe():
            return "ok"

        client = app.test_client()
        self.assertEqual(app.config["TRUSTED_HOSTS"], ["olumira.example.com"])
        self.assertEqual(
            client.get(
                "/transport-check", base_url="https://untrusted.invalid"
            ).status_code,
            400,
        )
        self.assertEqual(
            client.get(
                "/transport-check", base_url="http://olumira.example.com"
            ).status_code,
            308,
        )
        self.assertEqual(
            client.post(
                "/transport-check", base_url="http://olumira.example.com"
            ).status_code,
            400,
        )
        response = client.get(
            "/transport-check", base_url="https://olumira.example.com"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertIn("object-src 'none'", response.headers["Content-Security-Policy"])
        self.assertIn("microphone=()", response.headers["Permissions-Policy"])
        self.assertIn("max-age=", response.headers["Strict-Transport-Security"])
        # Untrusted forwarded proto is ignored with zero configured proxy hops.
        self.assertEqual(
            client.get(
                "/transport-check",
                base_url="http://olumira.example.com",
                headers={"X-Forwarded-Proto": "https"},
            ).status_code,
            308,
        )
        proxy = create_app(dict(values, TRUSTED_PROXY_HOPS=1))

        @proxy.get("/transport-check")
        def proxy_probe():
            return "ok"

        self.assertEqual(
            proxy.test_client()
            .get(
                "/transport-check",
                base_url="http://olumira.example.com",
                headers={"X-Forwarded-Proto": "https"},
            )
            .status_code,
            200,
        )

    def test_access_logs_redact_werkzeug_and_gunicorn_query_and_referrer_atoms(self):
        marker = "FICTIONAL-PRIVATE-QUERY"
        records = [
            logging.LogRecord(
                "werkzeug",
                20,
                "",
                0,
                "request %s",
                ("GET /observations?q=" + marker + " HTTP/1.1",),
                None,
            ),
            logging.LogRecord(
                "gunicorn.access",
                20,
                "",
                0,
                "%(r)s %(q)s %(f)s",
                {
                    "r": "GET /observations?q=" + marker + " HTTP/1.1",
                    "q": marker,
                    "f": "https://example.com/?token=" + marker,
                },
                None,
            ),
        ]
        for record in records:
            AccessPathFilter().filter(record)
            self.assertNotIn(marker, record.getMessage())
            self.assertIn("/observations", record.getMessage())
        configure_access_logging()
        configure_access_logging()
        for name in ["werkzeug", "gunicorn.access"]:
            self.assertEqual(
                sum(
                    isinstance(f, AccessPathFilter)
                    for f in logging.getLogger(name).filters
                ),
                1,
            )

    def test_security_events_accept_only_fixed_codes_and_internal_identifiers(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "qa_gunicorn_config", ROOT / "gunicorn.conf.py"
        )
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        logger = logging.getLogger("olumira")
        previous = logger.level
        try:
            config.post_fork(None, None)
            self.assertTrue(logger.isEnabledFor(logging.INFO))
        finally:
            logger.setLevel(previous)
        app = create_app({"APP_ENV": "testing"})
        with app.app_context():
            with self.assertLogs(app.logger, level="INFO") as logs:
                security_event("auth.login_success", "a" * 32)
                security_event("auth.login_failed")
            self.assertIn("auth.login_success", "".join(logs.output))
            self.assertNotIn("password=", "".join(logs.output))
            with self.assertRaises(ValueError):
                security_event("private arbitrary content")
            with self.assertRaises(ValueError):
                security_event("auth.logout", "email@example.com\nforged")

    def test_all_registered_mutations_remain_csrf_protected(self):
        app = create_app({"APP_ENV": "testing"})
        client = app.test_client()
        count = 0
        for rule in app.url_map.iter_rules():
            if "POST" not in rule.methods:
                continue
            values = {
                name: (
                    "1"
                    if "int" in type(rule._converters[name]).__name__.lower()
                    else "a" * 32
                )
                for name in rule.arguments
            }
            with app.test_request_context():
                path = rule.build(values)[1]
            response = client.post(path, data={})
            self.assertEqual(
                response.status_code, 400, (rule.endpoint, path, response.status_code)
            )
            count += 1
        self.assertGreater(count, 40)
