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


def log_request_failure(error):
    """Log exception identity and application stack only, never values/messages.

    SQLAlchemy/DBAPI exception strings and normal tracebacks can contain SQL
    parameters, credentials and care data. Do not use exc_info or format_exc here.
    """
    from pathlib import Path
    from flask import current_app, g, request

    root = Path(current_app.root_path).parent.resolve()
    frames = []
    trace = error.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        try:
            relative = Path(code.co_filename).resolve().relative_to(root)
        except ValueError:
            pass
        else:
            if relative.parts[0] in {'olumira', 'services'}:
                frames.append(f'{relative}:{trace.tb_lineno}:{code.co_name}')
        trace = trace.tb_next
    original = getattr(error, 'orig', None)
    sqlstate = getattr(original, 'sqlstate', None)
    if not isinstance(sqlstate, str) or not re.fullmatch(r'[A-Z0-9]{5}', sqlstate):
        sqlstate = 'unavailable'
    current_app.logger.error(
        'Request exception: request_id=%s endpoint=%s error_class=%s db_error_class=%s sqlstate=%s frames=%s',
        getattr(g, 'request_id', 'unavailable'), request.endpoint,
        type(error).__name__, type(original).__name__ if original is not None else 'none',
        sqlstate, '|'.join(frames) or 'outside_application',
    )


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
