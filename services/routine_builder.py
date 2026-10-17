"""Atomic, versioned routine editing within the existing family authorization boundary."""

import uuid
from flask import abort, g
from flask_login import current_user
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import Routine, RoutineStep, RoutineCompletion, CareProfile, utcnow
from services.workspaces import scope, require, care_audit
from services.database import transaction

ICONS = {
    "sun": "Sun",
    "leaf": "Leaf",
    "book": "Book",
    "calendar": "Calendar",
    "chat": "Conversation",
    "person": "Person",
    "note": "Note",
    "check": "Checkmark",
}
COLORS = {
    "sage": "Sage green",
    "peach": "Warm peach",
    "lavender": "Soft lavender",
    "sky": "Sky blue",
}
CATEGORIES = [
    "Morning",
    "Afternoon",
    "Evening",
    "Bedtime",
    "School",
    "Personal care",
    "Custom",
]
TEMPLATES = {
    "morning": dict(
        name="Morning preparation",
        category="Morning",
        icon="sun",
        color="sage",
        titles=[
            "Wake up gently",
            "Wash hands and face",
            "Choose clothes",
            "Enjoy breakfast",
            "Check the day ahead",
        ],
    ),
    "school": dict(
        name="Getting ready for school",
        category="School",
        icon="book",
        color="sky",
        titles=[
            "Choose clothes",
            "Have breakfast",
            "Brush teeth",
            "Pack the bag",
            "Take a calm moment",
        ],
    ),
    "bedtime": dict(
        name="Bedtime preparation",
        category="Bedtime",
        icon="leaf",
        color="lavender",
        titles=[
            "Put away activities",
            "Wash up",
            "Put on pajamas",
            "Choose a story",
            "Settle in",
        ],
    ),
    "bag": dict(
        name="Packing a bag",
        category="Custom",
        icon="calendar",
        color="peach",
        titles=[
            "Check the plan",
            "Choose what to bring",
            "Pack the essentials",
            "Check the bag",
        ],
    ),
    "activity": dict(
        name="Preparing for an activity",
        category="Afternoon",
        icon="leaf",
        color="sage",
        titles=[
            "Choose an activity",
            "Gather what helps",
            "Get comfortable",
            "Begin together",
        ],
    ),
}


class InvalidRoutine(ValueError):
    pass


class RoutineConflict(ValueError):
    pass


def steps_for(routine_id):
    return list(
        db.session.scalars(
            select(RoutineStep)
            .where(RoutineStep.routine_id == routine_id)
            .order_by(RoutineStep.position)
        )
    )


def find(routine_id, permission="routines.view", lock=False):
    require(permission, lock=lock)
    routine = db.session.scalar(
        select(Routine)
        .where(Routine.id == routine_id, scope(Routine, g.workspace_id))
        .execution_options(populate_existing=True)
    )
    if not routine:
        abort(404)
    return routine


def draft(routine):
    steps = steps_for(routine.id)
    return dict(
        name=routine.name,
        description=routine.description,
        category=routine.category,
        icon=routine.icon,
        color=routine.color,
        profile_id=routine.profile_id or "",
        version=routine.version,
        steps=[
            dict(
                id=step.id,
                title=step.title,
                description=step.description,
                icon=step.icon,
            )
            for step in steps
        ]
        or [dict(id="", title=routine.name, description="", icon=routine.icon)],
    )


def from_form(form):
    keys = ["step_id", "step_title", "step_description", "step_icon"]
    lists = {key: form.getlist(key) for key in keys}
    sizes = {len(values) for values in lists.values()}
    if len(sizes) != 1 or not 1 <= len(lists["step_title"]) <= 30:
        raise InvalidRoutine(
            "Add 1–30 complete steps. Each step needs a title, icon and description field."
        )
    values = {
        key: form.get(key, "")
        for key in [
            "name",
            "description",
            "category",
            "icon",
            "color",
            "profile_id",
            "version",
        ]
    }
    values["steps"] = [
        dict(
            id=lists["step_id"][i],
            title=lists["step_title"][i],
            description=lists["step_description"][i],
            icon=lists["step_icon"][i],
        )
        for i in range(len(lists["step_title"]))
    ]
    return values


def validate(values):
    clean = {
        key: str(values.get(key, "")).strip()
        for key in ["name", "description", "category", "icon", "color", "profile_id"]
    }
    if not clean["name"] or len(clean["name"]) > 80:
        raise InvalidRoutine("Give your routine a name of 1–80 characters.")
    if (
        not clean["category"]
        or len(clean["category"]) > 40
        or len(clean["description"]) > 1000
    ):
        raise InvalidRoutine(
            "Use a category up to 40 characters and a description up to 1,000."
        )
    if clean["icon"] not in ICONS or clean["color"] not in COLORS:
        raise InvalidRoutine("Choose one of the available icons and colors.")
    if clean["profile_id"] and not db.session.scalar(
        select(CareProfile.id).where(
            CareProfile.id == clean["profile_id"],
            CareProfile.workspace_id == g.workspace_id,
        )
    ):
        abort(404)
    steps = values.get("steps", [])
    if not isinstance(steps, list) or not 1 <= len(steps) <= 30:
        raise InvalidRoutine("Add between 1 and 30 steps.")
    ids = []
    clean_steps = []
    for step in steps:
        if not isinstance(step, dict):
            raise InvalidRoutine("Check the step information.")
        item = {
            key: str(step.get(key, "")).strip()
            for key in ["id", "title", "description", "icon"]
        }
        if (
            not item["title"]
            or len(item["title"]) > 80
            or len(item["description"]) > 500
            or item["icon"] not in ICONS
        ):
            raise InvalidRoutine(
                "Each step needs a title up to 80 characters, an available icon, and an optional description up to 500 characters."
            )
        if item["id"]:
            ids.append(item["id"])
        clean_steps.append(item)
    if len(ids) != len(set(ids)):
        raise InvalidRoutine(
            "A step was included more than once. Reload the saved routine and try again."
        )
    clean["profile_id"] = clean["profile_id"] or None
    return clean, clean_steps


def expected_version(routine, version):
    try:
        expected = int(version)
    except (ValueError, TypeError):
        raise RoutineConflict(
            "This form is missing its saved version. Reload before changing the routine."
        ) from None
    if expected != routine.version:
        raise RoutineConflict(
            "Another caregiver changed this routine. Your draft is still shown below. Open the latest saved version in a new tab and review both before saving again."
        )


def save(values, routine_id=None, *, checklist=False):
    with transaction():
        require("routines.edit" if routine_id else "routines.create", lock=True)
        clean, items = validate(values)
        routine = find(routine_id, "routines.edit") if routine_id else None
        if routine:
            expected_version(routine, values.get("version"))
            if routine.archived_at:
                raise InvalidRoutine("Restore this routine before editing it.")
            existing = {step.id: step for step in steps_for(routine.id)}
            if any(item["id"] and item["id"] not in existing for item in items):
                abort(404)
        else:
            if any(item["id"] for item in items):
                abort(404)
            count = db.session.scalar(
                select(func.count())
                .select_from(Routine)
                .where(
                    Routine.workspace_id == g.workspace_id,
                    Routine.profile_id == clean["profile_id"],
                    Routine.archived_at.is_(None),
                )
            )
            if count >= 40:
                raise InvalidRoutine(
                    "This profile already has 40 active routines. Archive one before adding another."
                )
            routine = Routine(
                owner_id=g.workspace_id,
                workspace_id=g.workspace_id,
                is_checklist=checklist,
                created_by=current_user.id,
            )
            db.session.add(routine)
            existing = {}
        old_profile = routine.profile_id
        if routine_id and old_profile != clean["profile_id"]:
            from olumira.models import RoutineSchedule, RoutineSession
            if any(db.session.scalar(select(model.id).where(model.routine_id == routine.id).limit(1)) for model in (RoutineSchedule, RoutineSession)):
                raise InvalidRoutine("This routine has schedules or saved runs. Duplicate it for another profile to preserve its history.")
        if (
            routine_id
            and old_profile != clean["profile_id"]
            and db.session.scalar(
                select(RoutineCompletion.routine_id)
                .where(RoutineCompletion.routine_id == routine.id)
                .limit(1)
            )
            is not None
        ):
            raise InvalidRoutine(
                "This routine has completion history. Duplicate it for another profile to keep that history with its original profile."
            )
        for key, value in clean.items():
            setattr(routine, key, value)
        if routine_id and old_profile != routine.profile_id:
            count = db.session.scalar(
                select(func.count())
                .select_from(Routine)
                .where(
                    Routine.workspace_id == g.workspace_id,
                    Routine.profile_id == routine.profile_id,
                    Routine.archived_at.is_(None),
                    Routine.id != routine.id,
                )
            )
            if count >= 40:
                raise InvalidRoutine(
                    "The destination profile already has 40 active routines."
                )
        if routine_id:
            routine.version += 1
        # Editing legacy daily checklists preserves their one-step semantics unless
        # the caregiver explicitly expands them into a multi-step routine.
        if len(items) > 1:
            routine.is_checklist = False
        db.session.flush()
        # Temporarily move positions above the entire old/new range; no negatives
        # or transient uniqueness violations while swapping positions.
        offset = (
            max([step.position for step in existing.values()] + [len(items)])
            + len(existing)
            + 1
        )
        for index, step in enumerate(existing.values()):
            step.position = offset + index
        db.session.flush()
        kept = {item["id"] for item in items if item["id"]}
        for step_id, step in existing.items():
            if step_id not in kept:
                db.session.delete(step)
        db.session.flush()
        for index, item in enumerate(items):
            step = existing.get(item["id"])
            if step is None:
                step = RoutineStep(id=uuid.uuid4().hex, routine_id=routine.id)
                db.session.add(step)
            step.title, step.description, step.icon, step.position = (
                item["title"],
                item["description"],
                item["icon"],
                index,
            )
        care_audit("routine.updated" if routine_id else "routine.created", routine.id)
        db.session.flush()
        result = (routine.id, routine.profile_id)
    return result


def change_archive(routine_id, version, restore=False):
    with transaction():
        routine = find(routine_id, "routines.edit", lock=True)
        expected_version(routine, version)
        if restore and routine.archived_at:
            count = db.session.scalar(
                select(func.count())
                .select_from(Routine)
                .where(scope(Routine, g.workspace_id), Routine.archived_at.is_(None))
            )
            if count >= 40:
                raise InvalidRoutine(
                    "Archive an active routine before restoring another."
                )
        if not restore:
            from services.routine_scheduling import pause_for_archive
            pause_for_archive(routine.id)
        routine.archived_at = None if restore else utcnow()
        routine.version += 1
        care_audit("routine.restored" if restore else "routine.archived", routine.id)


def duplicate(routine_id, profile_id):
    source = find(routine_id, "routines.create", lock=True)
    values = draft(source)
    values.update(name=(source.name[:73] + " (copy)"), profile_id=profile_id)
    for step in values["steps"]:
        step["id"] = ""
    return save(values, checklist=source.is_checklist)


def library(query="", category="", status="active", page=1):
    require("routines.view")
    if (
        len(query) > 100
        or len(category) > 40
        or status not in {"active", "archived", "all"}
        or not 1 <= page <= 10000
    ):
        abort(400)
    statement = select(Routine).where(scope(Routine, g.workspace_id))
    if status != "all":
        statement = statement.where(
            Routine.archived_at.is_not(None)
            if status == "archived"
            else Routine.archived_at.is_(None)
        )
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(
            Routine.name.ilike("%" + escaped + "%", escape="\\")
        )
    if category:
        statement = statement.where(Routine.category == category)
    total = db.session.scalar(select(func.count()).select_from(statement.subquery()))
    routines = list(
        db.session.scalars(
            statement.order_by(Routine.id.desc()).offset((page - 1) * 24).limit(24)
        )
    )
    ids = [r.id for r in routines]
    steps = (
        list(
            db.session.scalars(
                select(RoutineStep)
                .where(RoutineStep.routine_id.in_(ids))
                .order_by(RoutineStep.position)
            )
        )
        if ids
        else []
    )
    grouped = {routine.id: [] for routine in routines}
    for step in steps:
        grouped[step.routine_id].append(step)
    return routines, grouped, total


def dashboard_sequences(owner_id, limit=3):
    statement = select(Routine).where(
        scope(Routine, owner_id),
        Routine.archived_at.is_(None),
        Routine.is_checklist.is_(False),
    )
    count = db.session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = list(db.session.scalars(statement.order_by(Routine.id.desc()).limit(limit)))
    return rows, count


def categories_for_scope():
    values = db.session.scalars(
        select(Routine.category)
        .where(scope(Routine, g.workspace_id))
        .distinct()
        .order_by(Routine.category)
        .limit(100)
    )
    return sorted(set(CATEGORIES) | set(values))
