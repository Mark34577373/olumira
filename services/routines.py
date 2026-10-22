from services.workspaces import scope, association, care_audit
import uuid
from flask import has_request_context
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import (
    Routine,
    RoutineCompletion,
    RoutineStep,
    RoutineCompletionSnapshot,
    utcnow,
)
from services.database import today_string, transaction

MAX_ROUTINES = 40
ROUTINE_TEMPLATES = {
    "Morning": [
        "Wake up",
        "Brush teeth",
        "Get dressed",
        "Eat breakfast",
        "Pack backpack",
    ],
    "Meals": ["Wash hands", "Eat lunch", "Eat dinner", "Drink water"],
    "Bedtime": [
        "Bath or wash up",
        "Put on pajamas",
        "Brush teeth",
        "Read a book",
        "Lights out",
    ],
}


def _clean(name, category):
    name = (name or "").strip()
    category = (category or "").strip() or "General"
    return (
        (name, category)
        if name and len(name) <= 80 and len(category) <= 40
        else (None, None)
    )


def _count(owner_id):
    return db.session.scalar(
        select(func.count())
        .select_from(Routine)
        .where(scope(Routine, owner_id), Routine.archived_at.is_(None))
    )


def get_routines(owner_id, checklist_only=False):
    rows = db.session.execute(
        select(Routine, RoutineCompletion.routine_id)
        .outerjoin(
            RoutineCompletion,
            (RoutineCompletion.routine_id == Routine.id)
            & (RoutineCompletion.completion_date == today_string()),
        )
        .where(
            scope(Routine, owner_id),
            Routine.archived_at.is_(None),
            Routine.is_checklist.is_(True) if checklist_only else True,
        )
        .order_by(Routine.id)
    )
    return [
        dict(id=r.id, name=r.name, category=r.category, completed=int(done is not None))
        for r, done in rows
    ]


def group_by_category(routines):
    groups = {}
    for routine in routines:
        groups.setdefault(routine["category"], []).append(routine)
    return groups


def summarize_progress(routines):
    total = len(routines)
    completed = sum(r["completed"] for r in routines)
    return completed, total, round(completed / total * 100) if total else 0


def _owned(owner_id, routine_id):
    return db.session.scalar(
        select(Routine)
        .where(
            Routine.id == routine_id,
            scope(Routine, owner_id),
            Routine.archived_at.is_(None),
        )
        .with_for_update()
    )


def toggle_routine(owner_id, routine_id, desired=None, expected_date=None):
    with transaction() as session:
        routine = _owned(owner_id, routine_id)
        if routine is None or not routine.is_checklist:
            return False
        day = today_string()
        if expected_date is not None and expected_date != day:
            raise ValueError('The checklist date changed. Reload before continuing.')
        key = (routine_id, day)
        completion = session.get(RoutineCompletion, key)
        if desired is not None and bool(completion) == desired:
            return True
        care_audit("routine.completed_changed", routine_id)
        if completion:
            session.delete(completion)
        else:
            session.add(RoutineCompletion(routine_id=key[0], completion_date=key[1]))
            session.flush()
            if has_request_context():
                session.add(
                    RoutineCompletionSnapshot(
                        routine_id=key[0],
                        completion_date=key[1],
                        workspace_id=routine.workspace_id,
                        profile_id=routine.profile_id,
                        name=routine.name,
                        category=routine.category,
                        source="completion",
                    )
                )
    return True


def add_routine(owner_id, name, category):
    name, category = _clean(name, category)
    if not name:
        return "invalid"
    with transaction() as session:
        if _count(owner_id) >= MAX_ROUTINES:
            return "limit"
        routine = Routine(
            owner_id=owner_id, **association(), name=name, category=category
        )
        session.add(routine)
        session.flush()
        if has_request_context():
            session.add(
                RoutineStep(
                    id=uuid.uuid4().hex,
                    routine_id=routine.id,
                    title=name,
                    description="",
                    icon="sun",
                    position=0,
                )
            )
        care_audit("routine.created", routine.id)
    return "ok"


def update_routine(owner_id, routine_id, name, category, version=None):
    name, category = _clean(name, category)
    if not name:
        return "invalid"
    with transaction():
        routine = _owned(owner_id, routine_id)
        if routine is None:
            return "missing"
        if not routine.is_checklist:
            return "missing"
        if has_request_context() and str(version) != str(routine.version):
            return "conflict"
        routine.name, routine.category = name, category
        routine.version += 1
        step = db.session.scalar(
            select(RoutineStep).where(
                RoutineStep.routine_id == routine.id, RoutineStep.position == 0
            )
        )
        if step:
            step.title = name
        care_audit("routine.updated", routine.id)
    return "ok"


def delete_routine(owner_id, routine_id, version=None):
    with transaction() as session:
        routine = _owned(owner_id, routine_id)
        if routine is None:
            return False
        if has_request_context() and str(version) != str(routine.version):
            return "conflict"
        care_audit("routine.archived", routine.id)
        from services.routine_scheduling import pause_for_archive
        pause_for_archive(routine.id)
        routine.archived_at = utcnow()
        routine.version += 1
    return True


def add_template(owner_id, template_name):
    names = ROUTINE_TEMPLATES.get(template_name)
    if names is None:
        return "invalid"
    with transaction() as session:
        existing = set(
            session.scalars(
                select(Routine.name).where(
                    scope(Routine, owner_id),
                    Routine.archived_at.is_(None),
                    Routine.category == template_name,
                )
            )
        )
        new_names = [name for name in names if name not in existing]
        if _count(owner_id) + len(new_names) > MAX_ROUTINES:
            return "limit"
        care_audit("routine.template_added")
        for name in new_names:
            routine = Routine(
                owner_id=owner_id, **association(), name=name, category=template_name
            )
            session.add(routine)
            session.flush()
            if has_request_context():
                session.add(
                    RoutineStep(
                        id=uuid.uuid4().hex,
                        routine_id=routine.id,
                        title=name,
                        description="",
                        icon="sun",
                        position=0,
                    )
                )
    return "ok"
