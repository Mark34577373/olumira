"""Profile-bound plans reference existing care records; never copy them."""

import uuid
from datetime import date
from flask import abort, g
from flask_login import current_user
from sqlalchemy import select, delete, func
from olumira.extensions import db
from olumira.models import (
    CarePlan,
    CareGoal,
    CarePlanRoutine,
    CarePlanBoard,
    CarePlanTask,
    Routine,
    CommunicationBoard,
    CaregiverTask,
    Observation,
    RoutineSession,
    RoutineCompletion,
    User,
    WorkspaceMembership,
    utcnow,
)
from services.workspaces import require, scope, care_audit
from services.database import transaction, today_string
from services.care_coordination import reference
from services.communication import key, version

LINKS = {
    "routine_ids": (Routine, CarePlanRoutine, "routine_id"),
    "board_ids": (CommunicationBoard, CarePlanBoard, "board_id"),
    "task_ids": (CaregiverTask, CarePlanTask, "task_id"),
}


def find(identity, permission="care.view"):
    require(permission)
    row = db.session.scalar(
        select(CarePlan)
        .where(CarePlan.id == identity, scope(CarePlan, g.workspace_id))
        .execution_options(populate_existing=True)
    )
    if not row:
        abort(404)
    return row


def listing():
    require("care.view")
    query = select(CarePlan).where(scope(CarePlan, g.workspace_id))
    return list(
        db.session.scalars(query.order_by(CarePlan.updated_at.desc()).limit(100))
    )


def choices():
    require("care.view")
    return {
        name: list(
            db.session.scalars(
                select(model).where(scope(model, g.workspace_id)).limit(200)
            )
        )
        for name, (model, _, _) in LINKS.items()
    }


def selected(plan):
    return {
        name: [
            str(value)
            for value in db.session.scalars(
                select(getattr(link, column)).where(link.plan_id == plan.id)
            )
        ]
        for name, (_, link, column) in LINKS.items()
    }


def goal_values(values):
    title = str(values.get("title", "")).strip()
    description = str(values.get("description", "")).strip()
    category = str(values.get("category", "Daily support")).strip()
    status = values.get("status", "planned")
    target = values.get("target_date") or None
    if (
        not 1 <= len(title) <= 120
        or len(description) > 1000
        or not 1 <= len(category) <= 40
        or status not in {"planned", "in_progress", "completed", "paused"}
    ):
        raise ValueError(
            "Use a goal title up to 120 characters, notes up to 1,000 and an available status."
        )
    if target:
        try:
            if date.fromisoformat(target).isoformat() != target:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Choose a valid target date.") from None
    return dict(
        title=title,
        description=description,
        category=category,
        status=status,
        target_date=target,
    )


def save(values, links, identity=None):
    if not g.profile_id or values.get("profile_id") != g.profile_id:
        raise ValueError(
            "Select the care profile in the toolbar before building this plan."
        )
    title = values.get("title", "").strip()
    if (
        not 1 <= len(title) <= 120
        or any(len(values.get(k, "")) > 2000 for k in ["description", "priorities"])
        or values.get("status") not in {"draft", "active", "archived"}
    ):
        raise ValueError(
            "Use a title up to 120 characters, notes up to 2,000 and an available plan status."
        )
    with transaction():
        require("care.manage", lock=True)
        plan = find(identity, "care.manage") if identity else None
        if plan:
            version(plan, values.get("version"))
        else:
            identity = key(values.get("creation_key"))
            previous = db.session.get(CarePlan, identity)
            if previous:
                if (
                    previous.workspace_id,
                    previous.profile_id,
                    previous.created_by,
                ) != (g.workspace_id, g.profile_id, current_user.id):
                    abort(404)
                return previous.id
            if (
                db.session.scalar(
                    select(func.count())
                    .select_from(CarePlan)
                    .where(scope(CarePlan, g.workspace_id))
                )
                >= 100
            ):
                raise ValueError(
                    "This profile has 100 plans. Review existing plans before adding another."
                )
            plan = CarePlan(
                id=identity,
                workspace_id=g.workspace_id,
                profile_id=g.profile_id,
                created_by=current_user.id,
                version=0,
            )
        validated = {}
        for name, (model, link, column) in LINKS.items():
            ids = links.get(name, [])
            if len(ids) > 40 or len(ids) != len(set(ids)):
                raise ValueError("Select up to 40 different items in each section.")
            validated[name] = [reference(model, item, g.profile_id) for item in ids]
            if len({item.id for item in validated[name]}) != len(ids):
                raise ValueError("Select each connected item only once.")
        for field in ["title", "description", "priorities", "status"]:
            setattr(plan, field, values.get(field, "").strip())
        plan.updated_by = current_user.id
        plan.updated_at = utcnow()
        plan.version += 1
        db.session.add(plan)
        db.session.flush()
        for name, (_, link, column) in LINKS.items():
            db.session.execute(delete(link).where(link.plan_id == plan.id))
            for item in validated[name]:
                db.session.add(link(plan_id=plan.id, **{column: item.id}))
        if not values.get("version") and values.get("goal_title", "").strip():
            fields = goal_values(dict(title=values["goal_title"]))
            db.session.add(CareGoal(id=uuid.uuid4().hex, plan_id=plan.id, **fields))
        care_audit("care.plan_saved", plan.id)
        return plan.id


def save_goal(plan_id, values, goal_id=None):
    fields = goal_values(values)
    with transaction():
        require("care.manage", lock=True)
        plan = find(plan_id, "care.manage")
        version(plan, values.get("version"))
        goal = (
            db.session.scalar(
                select(CareGoal).where(
                    CareGoal.id == goal_id, CareGoal.plan_id == plan.id
                )
            )
            if goal_id
            else None
        )
        if goal_id and not goal:
            abort(404)
        if not goal:
            if (
                db.session.scalar(
                    select(func.count())
                    .select_from(CareGoal)
                    .where(CareGoal.plan_id == plan.id)
                )
                >= 50
            ):
                raise ValueError("Keep up to 50 goals per plan.")
            goal = CareGoal(id=uuid.uuid4().hex, plan_id=plan.id)
            db.session.add(goal)
        for field, value in fields.items():
            setattr(goal, field, value)
        plan.version += 1
        plan.updated_at = utcnow()
        plan.updated_by = current_user.id
        care_audit("care.goal_saved", plan.id)


def overview(plan):
    linked = {}
    for name, (model, link, column) in LINKS.items():
        linked[name] = list(
            db.session.scalars(
                select(model)
                .join(link, getattr(link, column) == model.id)
                .where(link.plan_id == plan.id, scope(model, g.workspace_id))
            )
        )
    linked["goals"] = list(
        db.session.scalars(
            select(CareGoal)
            .where(CareGoal.plan_id == plan.id)
            .order_by(CareGoal.created_at)
        )
    )
    linked["observations"] = list(
        db.session.scalars(
            select(Observation)
            .where(
                scope(Observation, g.workspace_id), Observation.archived_at.is_(None)
            )
            .order_by(Observation.created_at.desc())
            .limit(5)
        )
    )
    ids = [r.id for r in linked["routine_ids"]]
    linked["daily_completed"] = (
        db.session.scalar(
            select(func.count())
            .select_from(RoutineCompletion)
            .where(
                RoutineCompletion.routine_id.in_(ids),
                RoutineCompletion.completion_date == today_string(),
            )
        )
        or 0
    )
    linked["runs_today"] = (
        db.session.scalar(
            select(func.count())
            .select_from(RoutineSession)
            .where(
                scope(RoutineSession, g.workspace_id),
                RoutineSession.routine_id.in_(ids),
                RoutineSession.status == "completed",
                func.date(RoutineSession.completed_at) == utcnow().date(),
            )
        )
        or 0
    )
    linked["names"] = dict(
        db.session.execute(
            select(User.id, User.display_name)
            .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
            .where(WorkspaceMembership.workspace_id == g.workspace_id)
        ).all()
    )
    from services import calendar
    from services.database import now

    linked["upcoming"] = [
        item
        for item in calendar.events(now().date(), 1, str(now().tzinfo))
        if item["instant"] >= utcnow()
    ][:5]
    from olumira.models import AuditEvent

    linked["activity"] = db.session.execute(
        select(AuditEvent, User.display_name)
        .join(User, User.id == AuditEvent.actor_id)
        .where(
            AuditEvent.workspace_id == g.workspace_id,
            AuditEvent.target_id == plan.id,
            AuditEvent.event_type.in_(["care.plan_saved", "care.goal_saved"]),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(10)
    ).all()
    return linked
