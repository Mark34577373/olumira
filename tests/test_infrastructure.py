import importlib.util
import io
import json
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from cryptography.fernet import Fernet, InvalidToken
from flask_migrate import upgrade
from sqlalchemy import text

from olumira import create_app
from olumira.config import configuration
from olumira.extensions import db
from scripts.encrypted_backup import write_encrypted


def test_health_schema_and_dependency_failure():
    app = create_app({"APP_ENV": "testing"})
    client = app.test_client()
    assert client.get("/health/live").json == {"status": "alive"}
    assert client.get("/health/ready").status_code == 503
    with app.app_context():
        upgrade()
    assert client.get("/health/ready").json == {"status": "ready"}
    app.config["RATELIMIT_STORAGE_URI"] = "rediss://private.invalid"
    with patch("redis.Redis.from_url", side_effect=RuntimeError("secret-password")):
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json == {"status": "unavailable"}
    app.config["RATELIMIT_STORAGE_URI"] = "memory://"
    with app.app_context():
        db.session.execute(text("UPDATE alembic_version SET version_num='obsolete'"))
        db.session.commit()
    assert client.get("/health/ready").status_code == 503


def test_request_log_allowlist():
    app = create_app({"APP_ENV": "testing"})
    logger = logging.getLogger("olumira.operations")
    stream = io.StringIO()
    from olumira.infrastructure import OperationalFormatter

    handler = logging.StreamHandler(stream)
    handler.setFormatter(OperationalFormatter())
    logger.addHandler(handler)
    try:
        response = app.test_client().get(
            "/health/live?token=private", headers={"X-Request-ID": "private"}
        )
        record = json.loads(stream.getvalue())
        assert record["route"] == "/health/live"
        assert record["request_id"] == response.headers["X-Request-ID"]
        assert len(record["request_id"]) == 32
        assert "private" not in stream.getvalue()
    finally:
        logger.removeHandler(handler)


def test_encrypted_backup_exclusive_authenticated():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "backup.enc"
        key = Fernet.generate_key()
        payload = b"PGDMPfictional-sensitive-data"
        write_encrypted(payload, path, key)
        assert path.stat().st_mode & 0o777 == 0o600
        assert payload not in path.read_bytes()
        assert Fernet(key).decrypt(path.read_bytes()) == payload
        with pytest.raises(FileExistsError):
            write_encrypted(payload, path, key)
        with pytest.raises(InvalidToken):
            Fernet(Fernet.generate_key()).decrypt(path.read_bytes())
        with pytest.raises(ValueError):
            write_encrypted(b"not-a-dump", Path(directory) / "bad", key)


def test_gunicorn_resource_bounds():
    spec = importlib.util.spec_from_file_location(
        "gunicorn_settings", "gunicorn.conf.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.workers == 1 and module.threads == 2
    assert module.timeout > module.graceful_timeout
    assert module.forwarded_allow_ips == ""


def test_production_rejects_unverified_database_tls():
    from support import production_mail_settings

    settings = dict(
        APP_ENV="production",
        SECRET_KEY="fictional-production-key-of-sufficient-length",
        RATELIMIT_STORAGE_URI="redis://localhost:6379/15",
        **production_mail_settings()
    )
    for mode in ("disable", "require", "verify-ca", ""):
        with pytest.raises(ValueError, match="verify-full"):
            configuration(
                dict(
                    settings,
                    DATABASE_URL="postgresql://localhost/fictional?sslmode=" + mode,
                )
            )
    values = configuration(
        dict(
            settings,
            DATABASE_URL="postgresql://localhost/fictional?sslmode=verify-full",
        )
    )
    assert values["SQLALCHEMY_ENGINE_OPTIONS"]["max_overflow"] == 1
    app = create_app(
        dict(
            settings,
            DATABASE_URL="postgresql://localhost/fictional?sslmode=verify-full",
        )
    )
    assert (
        app.test_client()
        .get("/health/live", base_url="http://olumira.example.com")
        .status_code
        == 200
    )


def test_operations_continues_after_failure_and_reports_failure():
    from scripts.run_operations import main, COMMANDS

    with patch("scripts.run_operations.subprocess.run") as run:
        run.side_effect = [MagicMock(returncode=1)] + [MagicMock(returncode=0)] * 3
        assert main() == 1
        assert run.call_count == len(COMMANDS)
    with patch(
        "scripts.run_operations.subprocess.run", return_value=MagicMock(returncode=0)
    ):
        assert main() == 0


def test_migration_requires_separate_secret_and_refuses_concurrent_runner():
    from scripts.migrate_release import main

    with patch.dict(os.environ, {"MIGRATION_DATABASE_URL": ""}):
        with pytest.raises(ValueError, match="MIGRATION_DATABASE_URL"):
            main()
    fake = MagicMock()
    fake.__enter__.return_value.execute.return_value.fetchone.return_value = (False,)
    app = create_app(
        {
            "APP_ENV": "testing",
            "DATABASE_URL": "postgresql+psycopg://qa@localhost/fictional",
        }
    )
    with patch.dict(
        os.environ, {"MIGRATION_DATABASE_URL": "postgresql://qa@localhost/fictional"}
    ), patch("olumira.create_app", return_value=app), patch(
        "psycopg.connect", return_value=fake
    ), patch(
        "flask_migrate.upgrade"
    ) as upgrade_mock:
        with pytest.raises(RuntimeError, match="Another migration"):
            main()
        upgrade_mock.assert_not_called()
