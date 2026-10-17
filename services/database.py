"""Shared time helpers and transactional visitor-workspace provisioning."""
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import current_app
from olumira.extensions import db
from olumira.models import Owner, Routine

STARTER_ROUTINES = [
    ('Wake up', 'Morning'), ('Brush teeth', 'Morning'), ('Get dressed', 'Morning'),
    ('Eat breakfast', 'Morning'), ('Pack backpack', 'Morning'),
]


def now():
    return datetime.now(ZoneInfo(current_app.config['APP_TIMEZONE']))


def today_string():
    return now().date().isoformat()


def time_greeting():
    hour = now().hour
    return 'Good morning' if hour < 12 else 'Good afternoon' if hour < 17 else 'Good evening'


@contextmanager
def transaction():
    """Services own the commit boundary; failed writes always roll back."""
    try:
        yield db.session
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def ensure_workspace(owner_id):
    with transaction() as session:
        if session.get(Owner, owner_id) is None:
            session.add(Owner(id=owner_id, created_at=today_string()))
            session.add_all(Routine(owner_id=owner_id, name=name, category=category)
                            for name, category in STARTER_ROUTINES)
