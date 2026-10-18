"""Suite-wide fail-closed guard: tests may mock mail, never deliver it."""

import smtplib
import pytest


@pytest.fixture(autouse=True)
def no_real_smtp(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError(
            "Real SMTP delivery is forbidden in tests; mock the transport"
        )

    monkeypatch.setattr(smtplib, "SMTP", blocked)
    monkeypatch.setattr(smtplib, "SMTP_SSL", blocked)


@pytest.fixture(autouse=True)
def dispose_auxiliary_test_engines():
    """Close pools from secondary factory apps as well as each fixture's main app."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    engines = set()

    def connected(connection):
        engines.add(connection.engine)

    event.listen(Engine, "engine_connect", connected)
    try:
        yield
    finally:
        event.remove(Engine, "engine_connect", connected)
        for engine in engines:
            engine.dispose()
