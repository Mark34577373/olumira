"""Private-data-free operational probes and request telemetry."""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import text

bp = Blueprint("health", __name__)


@bp.get("/health/live")
def live():
    return jsonify(status="alive")


@bp.get("/health/ready")
def ready():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from redis import Redis
    from .extensions import db

    try:
        config = Config()
        config.set_main_option(
            "script_location", str(Path(current_app.root_path).parent / "migrations")
        )
        expected = set(ScriptDirectory.from_config(config).get_heads())
        with db.engine.connect() as connection:
            actual = set(
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalars()
            )
        if actual != expected:
            raise RuntimeError("schema")
        uri = current_app.config["RATELIMIT_STORAGE_URI"]
        if uri.startswith(("redis://", "rediss://")):
            client = Redis.from_url(uri, socket_connect_timeout=2, socket_timeout=2)
            try:
                if not client.ping():
                    raise RuntimeError("rate storage")
            finally:
                client.close()
    except Exception:
        # Never disclose connection strings, dependency names or exception text.
        return jsonify(status="unavailable"), 503
    return jsonify(status="ready")


class OperationalFormatter(logging.Formatter):
    """Allowlisted fields only: no formatted messages or exception payloads."""

    def format(self, record):
        return json.dumps(
            dict(
                timestamp=datetime.now(timezone.utc).isoformat(),
                severity=record.levelname,
                category="http",
                operation="request",
                request_id=record.request_id,
                route=record.route,
                status=record.status,
                duration_ms=record.duration_ms,
            ),
            separators=(",", ":"),
        )


def register(app):
    app.register_blueprint(bp)
    logger = logging.getLogger("olumira.operations")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(OperationalFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    @app.before_request
    def request_start():
        g.request_id = uuid.uuid4().hex  # Do not trust client-provided log identifiers.
        g.request_started = time.monotonic()

    @app.after_request
    def request_end(response):
        identifier = getattr(g, "request_id", uuid.uuid4().hex)
        response.headers["X-Request-ID"] = identifier
        logger.info(
            "request",
            extra=dict(
                request_id=identifier,
                route=request.url_rule.rule if request.url_rule else "unmatched",
                status=response.status_code,
                duration_ms=round(
                    (time.monotonic() - getattr(g, "request_started", time.monotonic()))
                    * 1000,
                    2,
                ),
            ),
        )
        return response
