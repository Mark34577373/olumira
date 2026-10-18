"""Minimize access/security logs without retaining private query values or tokens."""

import logging
import re


def request_line(value):
    if not isinstance(value, str):
        return value
    return re.sub(
        r"([A-Z]+ )([^ ]+)( HTTP/\d(?:\.\d)?)",
        lambda m: m[1] + m[2].split("?", 1)[0].split("#", 1)[0] + m[3],
        value,
    )


class AccessPathFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(request_line(value) for value in record.args)
        elif isinstance(record.args, dict):
            # Gunicorn's default request/referrer atoms, plus custom query atoms.
            atoms = dict(record.args)
            for key in ("r",):
                if key in atoms:
                    atoms[key] = request_line(atoms[key])
            for key in ("U",):
                if isinstance(atoms.get(key), str):
                    atoms[key] = atoms[key].split("?", 1)[0].split("#", 1)[0]
            for key in ("q", "f", "{referer}i", "{referrer}i"):
                if key in atoms:
                    atoms[key] = "[redacted]"
            record.args = atoms
        record.msg = request_line(record.msg)
        return True


def configure_access_logging():
    for name in ("werkzeug", "gunicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, AccessPathFilter) for item in logger.filters):
            logger.addFilter(AccessPathFilter())


SECURITY_EVENTS = frozenset(
    {
        "auth.login_success",
        "auth.login_failed",
        "auth.logout",
        "auth.email_verified",
        "auth.password_reset",
        "auth.email_changed",
        "auth.profile_updated",
        "auth.email_change_requested",
        "auth.email_change_cancelled",
        "auth.password_changed",
        "auth.sessions_revoked",
    }
)


def security_event(event, actor_id=None):
    """Fixed event + internal actor ID only; never accept arbitrary payload fields."""
    from flask import current_app

    if event not in SECURITY_EVENTS:
        raise ValueError("Unsupported security event")
    if actor_id is not None and not re.fullmatch(r"[a-f0-9]{32}", str(actor_id)):
        raise ValueError("Unsupported actor identifier")
    current_app.logger.log(
        logging.WARNING if event.endswith("_failed") else logging.INFO,
        "security event=%s actor=%s",
        event,
        actor_id or "anonymous",
    )
