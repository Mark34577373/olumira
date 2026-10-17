"""Shared time helpers and transactional visitor-workspace provisioning."""

from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text
from flask import current_app
from olumira.extensions import db
from olumira.models import Owner, Routine

STARTER_ROUTINES = [
    ("Wake up", "Morning"),
    ("Brush teeth", "Morning"),
    ("Get dressed", "Morning"),
    ("Eat breakfast", "Morning"),
    ("Pack backpack", "Morning"),
]


def now():
    return datetime.now(ZoneInfo(current_app.config["APP_TIMEZONE"]))


def today_string():
    return now().date().isoformat()


def time_greeting():
    hour = now().hour
    return (
        "Good morning"
        if hour < 12
        else "Good afternoon" if hour < 17 else "Good evening"
    )


@contextmanager
def transaction():
    """Compose service writes atomically; only the outer boundary commits."""
    store = db.session()
    depth = store.info.get("olumira_transaction_depth", 0)
    store.info["olumira_transaction_depth"] = depth + 1
    try:
        yield store
        if depth == 0:
            if store.info.pop("olumira_transaction_failed", False):
                raise RuntimeError(
                    "A nested transaction failed; changes were rolled back."
                )
            store.commit()
    except Exception:
        store.info["olumira_transaction_failed"] = True
        if depth == 0:
            store.rollback()
        raise
    finally:
        if depth:
            store.info["olumira_transaction_depth"] = depth
        else:
            store.info.pop("olumira_transaction_depth", None)
            store.info.pop("olumira_transaction_failed", None)


def ensure_workspace(owner_id):
    with transaction() as session:
        if session.get(Owner, owner_id) is None:
            session.add(Owner(id=owner_id, created_at=today_string()))
            session.flush()
            session.execute(
                text(
                    "INSERT INTO routines (owner_id,name,category) VALUES (:owner,:name,:category)"
                ),
                [
                    dict(owner=owner_id, name=name, category=category)
                    for name, category in STARTER_ROUTINES
                ],
            )
