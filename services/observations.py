from services.workspaces import scope, association, care_audit
from flask import has_request_context
from datetime import date as calendar_date
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import Observation
from services.database import transaction

MAX_OBSERVATIONS = 300


def add_observation(owner_id, activity, date, notes, mood, tags):
    if has_request_context():
        from services.journal import save

        try:
            return save(
                dict(activity=activity, date=date, notes=notes, mood=mood, tags=tags)
            )
        except ValueError:
            return None
    values = dict(
        activity=(activity or "").strip(),
        date=(date or "").strip(),
        notes=(notes or "").strip(),
        mood=(mood or "").strip(),
        tags=(tags or "").strip(),
    )
    try:
        if calendar_date.fromisoformat(values["date"]).isoformat() != values["date"]:
            return None
    except ValueError:
        return None
    limits = dict(activity=120, date=10, notes=2000, mood=20, tags=120)
    if not values["activity"] or any(
        len(values[key]) > limit for key, limit in limits.items()
    ):
        return None
    with transaction() as session:
        if (
            session.scalar(
                select(func.count())
                .select_from(Observation)
                .where(scope(Observation, owner_id))
            )
            >= MAX_OBSERVATIONS
        ):
            return None
        observation = Observation(owner_id=owner_id, **association(), **values)
        session.add(observation)
        session.flush()
        result = observation.id
        care_audit("observation.created", result)
    return result


def get_observations(owner_id, limit=None):
    from services.journal import chronology

    query = (
        select(Observation)
        .where(scope(Observation, owner_id), Observation.archived_at.is_(None))
        .order_by(*chronology())
    )
    if limit is not None:
        query = query.limit(limit)
    return [
        dict(
            id=o.id,
            owner_id=o.owner_id,
            activity=o.activity,
            date=o.date,
            notes=o.notes,
            mood=o.mood,
            tags=o.tags,
            category=o.category,
            observed_at=o.observed_at,
            timezone=o.timezone,
        )
        for o in db.session.scalars(query)
    ]


def edit_observation(owner_id, observation_id, values):
    if has_request_context():
        from services.journal import save

        try:
            save(values, observation_id)
        except ValueError:
            return "invalid"
        return "ok"
    clean = {
        key: (values.get(key) or "").strip()
        for key in ("activity", "date", "notes", "mood", "tags")
    }
    try:
        valid = calendar_date.fromisoformat(clean["date"]).isoformat() == clean["date"]
    except ValueError:
        valid = False
    limits = dict(activity=120, date=10, notes=2000, mood=20, tags=120)
    if (
        not valid
        or not clean["activity"]
        or any(len(clean[key]) > limit for key, limit in limits.items())
    ):
        return "invalid"
    with transaction():
        observation = db.session.scalar(
            select(Observation)
            .where(Observation.id == observation_id, scope(Observation, owner_id))
            .with_for_update()
        )
        if not observation:
            return "missing"
        for key, value in clean.items():
            setattr(observation, key, value)
        care_audit("observation.updated", observation.id)
    return "ok"
