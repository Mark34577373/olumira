from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import Routine, RoutineCompletion
from services.database import today_string, transaction

MAX_ROUTINES = 40
ROUTINE_TEMPLATES = {
    'Morning': ['Wake up', 'Brush teeth', 'Get dressed', 'Eat breakfast', 'Pack backpack'],
    'Meals': ['Wash hands', 'Eat lunch', 'Eat dinner', 'Drink water'],
    'Bedtime': ['Bath or wash up', 'Put on pajamas', 'Brush teeth', 'Read a book', 'Lights out'],
}


def _clean(name, category):
    name = (name or '').strip()
    category = (category or '').strip() or 'General'
    return (name, category) if name and len(name) <= 80 and len(category) <= 40 else (None, None)


def _count(owner_id):
    return db.session.scalar(select(func.count()).select_from(Routine).where(Routine.owner_id == owner_id))


def get_routines(owner_id):
    rows = db.session.execute(select(Routine, RoutineCompletion.routine_id).outerjoin(
        RoutineCompletion, (RoutineCompletion.routine_id == Routine.id) &
        (RoutineCompletion.completion_date == today_string())
    ).where(Routine.owner_id == owner_id).order_by(Routine.id))
    return [dict(id=r.id, name=r.name, category=r.category, completed=int(done is not None)) for r, done in rows]


def group_by_category(routines):
    groups = {}
    for routine in routines:
        groups.setdefault(routine['category'], []).append(routine)
    return groups


def summarize_progress(routines):
    total = len(routines)
    completed = sum(r['completed'] for r in routines)
    return completed, total, round(completed / total * 100) if total else 0


def _owned(owner_id, routine_id):
    return db.session.scalar(select(Routine).where(Routine.id == routine_id, Routine.owner_id == owner_id).with_for_update())


def toggle_routine(owner_id, routine_id):
    with transaction() as session:
        if _owned(owner_id, routine_id) is None:
            return False
        key = (routine_id, today_string())
        completion = session.get(RoutineCompletion, key)
        if completion:
            session.delete(completion)
        else:
            session.add(RoutineCompletion(routine_id=key[0], completion_date=key[1]))
    return True


def add_routine(owner_id, name, category):
    name, category = _clean(name, category)
    if not name:
        return 'invalid'
    with transaction() as session:
        if _count(owner_id) >= MAX_ROUTINES:
            return 'limit'
        session.add(Routine(owner_id=owner_id, name=name, category=category))
    return 'ok'


def update_routine(owner_id, routine_id, name, category):
    name, category = _clean(name, category)
    if not name:
        return 'invalid'
    with transaction():
        routine = _owned(owner_id, routine_id)
        if routine is None:
            return 'missing'
        routine.name, routine.category = name, category
    return 'ok'


def delete_routine(owner_id, routine_id):
    with transaction() as session:
        routine = _owned(owner_id, routine_id)
        if routine is None:
            return False
        session.delete(routine)
    return True


def add_template(owner_id, template_name):
    names = ROUTINE_TEMPLATES.get(template_name)
    if names is None:
        return 'invalid'
    with transaction() as session:
        existing = set(session.scalars(select(Routine.name).where(Routine.owner_id == owner_id, Routine.category == template_name)))
        new_names = [name for name in names if name not in existing]
        if _count(owner_id) + len(new_names) > MAX_ROUTINES:
            return 'limit'
        session.add_all(Routine(owner_id=owner_id, name=name, category=template_name) for name in new_names)
    return 'ok'
