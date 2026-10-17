from datetime import date as calendar_date
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import Observation
from services.database import transaction

MAX_OBSERVATIONS = 300


def add_observation(owner_id, activity, date, notes, mood, tags):
    values = dict(activity=(activity or '').strip(), date=(date or '').strip(),
                  notes=(notes or '').strip(), mood=(mood or '').strip(), tags=(tags or '').strip())
    try:
        if calendar_date.fromisoformat(values['date']).isoformat() != values['date']:
            return None
    except ValueError:
        return None
    limits = dict(activity=120, date=10, notes=2000, mood=20, tags=120)
    if not values['activity'] or any(len(values[key]) > limit for key, limit in limits.items()):
        return None
    with transaction() as session:
        if session.scalar(select(func.count()).select_from(Observation).where(Observation.owner_id == owner_id)) >= MAX_OBSERVATIONS:
            return None
        observation = Observation(owner_id=owner_id, **values)
        session.add(observation)
        session.flush()
        result = observation.id
    return result


def get_observations(owner_id, limit=None):
    query = select(Observation).where(Observation.owner_id == owner_id).order_by(Observation.date.desc(), Observation.id.desc())
    if limit is not None:
        query = query.limit(limit)
    return [dict(id=o.id, owner_id=o.owner_id, activity=o.activity, date=o.date, notes=o.notes, mood=o.mood, tags=o.tags)
            for o in db.session.scalars(query)]
