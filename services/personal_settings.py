"""User display preferences, independent of shared profile settings."""

from types import SimpleNamespace
from flask import abort
from flask_login import current_user
from sqlalchemy import select, update
from olumira.extensions import db
from olumira.models import UserPreference, User
from services.database import transaction

FLAGS = (
    "larger_text",
    "reduced_motion",
    "enhanced_contrast",
    "simplified",
    "reduced_effects",
)
CHOICES = {
    "calendar_view": ("month", "week", "day", "agenda"),
    "week_start": ("monday", "sunday"),
    "time_format": ("24", "12"),
}


def get():
    return db.session.get(UserPreference, current_user.id) or SimpleNamespace(
        version=0,
        **dict.fromkeys(FLAGS, False),
        calendar_view="month",
        week_start="monday",
        time_format="24"
    )


def save(values):
    if not current_user.is_authenticated or not current_user.email_verified:
        abort(403)
    clean = {}
    for field, allowed in CHOICES.items():
        if values.get(field) not in allowed:
            raise ValueError("Choose a supported calendar option.")
        clean[field] = values[field]
    name = values.get("display_name", "").strip()
    if not 1 <= len(name) <= 80:
        raise ValueError("Use a display name of 1–80 characters.")
    with transaction():
        db.session.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(updated_at=User.updated_at)
        )
        pref = db.session.scalar(
            select(UserPreference)
            .where(UserPreference.user_id == current_user.id)
            .execution_options(populate_existing=True)
        )
        if str(pref.version if pref else 0) != values.get("version"):
            raise ValueError("Settings changed. Reload before saving.")
        if pref is None:
            pref = UserPreference(user_id=current_user.id, version=0)
            db.session.add(pref)
        for field, value in clean.items():
            setattr(pref, field, value)
        for field in FLAGS:
            if values.get(field, "") not in ("", "on"):
                raise ValueError("Choose a valid accessibility option.")
            setattr(pref, field, values.get(field) == "on")
        pref.version += 1
        current_user.display_name = name
