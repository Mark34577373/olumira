"""Profile-scoped responsibilities and immutable handoffs, using existing audit events."""

import re, uuid
from datetime import datetime, timedelta, timezone, time
from flask import abort, g, current_app
from flask_login import current_user
from sqlalchemy import select, func, exists, or_, cast, String
from olumira.extensions import db
from olumira.models import (
    CaregiverTask as Task,
    CaregiverHandoff as Handoff,
    HandoffRecipient as Recipient,
    HandoffTask,
    WorkspaceMembership as Member,
    User,
    CareProfile,
    Routine,
    RoutineSession,
    Observation,
    CommunicationBoard,
    AuditEvent,
    utcnow,
)
from services.workspaces import require, scope, care_audit
from services.database import transaction
from services.communication import (
    key,
    version,
    InvalidCommunication as InvalidCare,
    CommunicationConflict as CareConflict,
)
from services.routine_scheduling import zone, parse_date, local_instant, aware

STATUSES = {
    "todo": "To do",
    "in_progress": "In progress",
    "completed": "Completed",
    "canceled": "Canceled",
}
TRANSITIONS = {
    "todo": {"in_progress", "completed", "canceled"},
    "in_progress": {"todo", "completed", "canceled"},
    "completed": {"todo"},
    "canceled": {"todo"},
}


def members():
    require("care.view")
    return db.session.execute(
        select(Member, User.display_name)
        .join(User, User.id == Member.user_id)
        .where(
            Member.workspace_id == g.workspace_id,
            Member.status == "active",
            Member.role.in_(["owner", "caregiver"]),
        )
        .order_by(User.display_name)
        .limit(100)
    ).all()


def validate_member(user_id):
    if not user_id:
        return None
    if not db.session.scalar(
        select(Member.id).where(
            Member.workspace_id == g.workspace_id,
            Member.user_id == user_id,
            Member.status == "active",
            Member.role.in_(["owner", "caregiver"]),
        )
    ):
        raise InvalidCare("Choose an active owner or caregiver from this workspace.")
    return user_id


def validate_profile(profile_id):
    profile_id = profile_id or None
    if profile_id and not db.session.scalar(
        select(CareProfile.id).where(
            CareProfile.id == profile_id, CareProfile.workspace_id == g.workspace_id
        )
    ):
        abort(404)
    return profile_id


def reference(model, identity, profile_id):
    if not identity:
        return None
    try:
        identity = int(identity) if model in {Routine, Observation} else identity
    except (ValueError, TypeError):
        raise InvalidCare("Choose a valid related item.") from None
    item = db.session.scalar(
        select(model).where(
            model.id == identity,
            model.workspace_id == g.workspace_id,
            model.profile_id == profile_id,
        )
    )
    if not item:
        abort(404)
    return item


def find(model, identity, permission="care.view"):
    require(permission)
    item = db.session.scalar(
        select(model)
        .where(model.id == identity, scope(model, g.workspace_id))
        .execution_options(populate_existing=True)
    )
    if not item:
        abort(404)
    return item


def parse_due(raw, tz):
    zone(tz)
    if not raw:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", raw):
        raise InvalidCare("Choose a valid due date and time.")
    try:
        instant = local_instant(parse_date(raw[:10]), raw[11:], tz)
    except (ValueError, TypeError):
        raise InvalidCare("Choose a valid due date and time.") from None
    if instant is None:
        raise InvalidCare(
            "That due time does not exist during the daylight-saving change. Choose another time."
        )
    return instant


def save_task(values, identity=None):
    title = (values.get("title") or "").strip()
    description = (values.get("description") or "").strip()
    if (
        not 1 <= len(title) <= 120
        or len(description) > 2000
        or values.get("priority") not in {"low", "normal", "high"}
    ):
        raise InvalidCare(
            "Use a task title of 1–120 characters, notes up to 2,000 and an available priority."
        )
    with transaction():
        require("care.manage", lock=True)
        profile_id = validate_profile(values.get("profile_id"))
        task = find(Task, identity, "care.manage") if identity else None
        if task:
            version(task, values.get("version"))
            if task.profile_id != profile_id:
                raise InvalidCare(
                    "A saved task keeps its original profile. Create a new task for another profile."
                )
        else:
            identity = key(values.get("creation_key"))
            previous = db.session.get(Task, identity)
            if previous:
                if (
                    previous.workspace_id,
                    previous.profile_id,
                    previous.created_by,
                ) != (g.workspace_id, profile_id, current_user.id):
                    abort(404)
                return previous.id, previous.profile_id
            if (
                db.session.scalar(
                    select(func.count())
                    .select_from(Task)
                    .where(
                        Task.workspace_id == g.workspace_id,
                        Task.profile_id == profile_id,
                        Task.status.in_(["todo", "in_progress"]),
                    )
                )
                >= 200
            ):
                raise InvalidCare(
                    "This profile has 200 open tasks. Finish or cancel a task before adding another."
                )
            task = Task(
                id=identity,
                workspace_id=g.workspace_id,
                profile_id=profile_id,
                created_by=current_user.id,
                status="todo",
                version=0,
            )
        assignee = validate_member(values.get("assigned_to"))
        routine = reference(Routine, values.get("routine_id"), profile_id)
        if routine and routine.archived_at:
            raise InvalidCare("Choose an active related routine.")
        due = parse_due(values.get("due_at", ""), values.get("timezone", ""))
        changed_assignee = task.assigned_to != assignee
        for field, value in dict(
            title=title,
            description=description,
            assigned_to=assignee,
            routine_id=routine.id if routine else None,
            due_at=due,
            timezone=values["timezone"],
            priority=values["priority"],
        ).items():
            setattr(task, field, value)
        db.session.add(task)
        task.version += 1
        care_audit(
            "care.task_created" if not values.get("version") else "care.task_updated",
            task.id,
        )
        if changed_assignee:
            care_audit("care.task_assigned", task.id)
            if assignee:
                from services.notifications import emit

                emit(
                    assignee,
                    g.workspace_id,
                    profile_id,
                    "task",
                    "task",
                    task.id,
                    f"task:{task.id}:assignment:{task.version}",
                    "assigned",
                )
        result = task.id, profile_id
    return result


def change_status(identity, status, expected):
    if status not in STATUSES:
        abort(400)
    with transaction():
        require("care.manage", lock=True)
        task = find(Task, identity, "care.manage")
        if task.status == status:
            return  # Desired-state completion retries never toggle/re-complete.
        version(task, expected)
        if status not in TRANSITIONS[task.status]:
            raise InvalidCare("Reopen this task before choosing another status.")
        task.status = status
        task.version += 1
        task.completed_at = utcnow() if status == "completed" else None
        task.completed_by = current_user.id if status == "completed" else None
        care_audit(
            "care.task_"
            + (
                "completed"
                if status == "completed"
                else "reopened" if status == "todo" else status
            ),
            task.id,
        )


def task_query(filters):
    query = select(Task).where(scope(Task, g.workspace_id))
    view = filters.get("view", "all")
    status = filters.get("status", "")
    if view not in {"all", "my", "upcoming", "overdue", "completed"}:
        abort(400)
    now = utcnow()
    if view == "my":
        query = query.where(Task.assigned_to == current_user.id)
    if view == "completed":
        status = "completed"
    if view in {"overdue", "upcoming"}:
        query = query.where(
            Task.status.in_(["todo", "in_progress"]),
            (
                Task.due_at < now
                if view == "overdue"
                else (Task.due_at >= now) & (Task.due_at <= now + timedelta(days=7))
            ),
        )
    if status:
        if status not in STATUSES:
            abort(400)
        query = query.where(Task.status == status)
    if filters.get("assignee"):
        query = query.where(Task.assigned_to == filters["assignee"])
    return query


def task_list(filters, page=1):
    require("care.view")
    if not 1 <= page <= 10000:
        abort(400)
    query = task_query(filters)
    count = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(
        db.session.scalars(
            query.order_by(
                Task.due_at.asc().nullslast(), Task.created_at.desc(), Task.id
            )
            .offset((page - 1) * 20)
            .limit(20)
        )
    )
    return rows, count


def reference_choices():
    return dict(
        tasks=list(
            db.session.scalars(
                select(Task)
                .where(scope(Task, g.workspace_id))
                .order_by(Task.updated_at.desc())
                .limit(200)
            )
        ),
        routines=list(
            db.session.scalars(
                select(Routine)
                .where(scope(Routine, g.workspace_id), Routine.archived_at.is_(None))
                .order_by(Routine.name)
                .limit(40)
            )
        ),
        observations=list(
            db.session.scalars(
                select(Observation)
                .where(scope(Observation, g.workspace_id))
                .order_by(Observation.date.desc())
                .limit(100)
            )
        ),
    )


def create_handoff(values, task_ids):
    summary = (values.get("summary") or "").strip()
    if (
        not 1 <= len(summary) <= 2000
        or len(task_ids) > 10
        or len(set(task_ids)) != len(task_ids)
    ):
        raise InvalidCare(
            "Use a summary of 1–2,000 characters and up to ten different related tasks."
        )
    with transaction():
        require("care.manage", lock=True)
        profile_id = validate_profile(values.get("profile_id"))
        identity = key(values.get("creation_key"))
        previous = db.session.get(Handoff, identity)
        if previous:
            if (previous.workspace_id, previous.profile_id, previous.created_by) != (
                g.workspace_id,
                profile_id,
                current_user.id,
            ):
                abort(404)
            return previous.id, previous.profile_id
        recipient = values.get("recipient", "")
        recipients = (
            [
                member.user_id
                for member, _ in members()
                if member.user_id != current_user.id
            ]
            if recipient == "team"
            else [validate_member(recipient)]
        )
        if not recipients or None in recipients or current_user.id in recipients:
            raise InvalidCare(
                "Choose another active caregiver, or a team with at least one other caregiver."
            )
        if (
            db.session.scalar(
                select(func.count())
                .select_from(Handoff)
                .where(
                    Handoff.workspace_id == g.workspace_id,
                    Handoff.profile_id == profile_id,
                )
            )
            >= 1000
        ):
            raise InvalidCare(
                "This profile has reached its 1,000 saved handoffs. Contact the workspace owner about retention before adding more."
            )
        tasks = [reference(Task, tid, profile_id) for tid in task_ids]
        routine = reference(Routine, values.get("routine_id"), profile_id)
        observation = reference(Observation, values.get("observation_id"), profile_id)
        handoff = Handoff(
            id=identity,
            workspace_id=g.workspace_id,
            profile_id=profile_id,
            summary=summary,
            recipient_kind="team" if recipient == "team" else "person",
            routine_id=routine.id if routine else None,
            observation_id=observation.id if observation else None,
            created_by=current_user.id,
        )
        db.session.add(handoff)
        db.session.flush()
        for uid in recipients:
            db.session.add(Recipient(handoff_id=identity, user_id=uid))
            from services.notifications import emit

            emit(
                uid,
                g.workspace_id,
                profile_id,
                "handoff",
                "handoff",
                identity,
                "handoff:" + identity,
                "handoff",
            )
        for task in tasks:
            db.session.add(HandoffTask(handoff_id=identity, task_id=task.id))
        care_audit("care.handoff_created", identity)
        result = identity, profile_id
    return result


def acknowledge(identity):
    with transaction():
        require("care.acknowledge", lock=True)
        handoff = find(Handoff, identity, "care.acknowledge")
        recipient = db.session.get(Recipient, (handoff.id, current_user.id))
        if not recipient:
            abort(403)
        if recipient.acknowledged_at:
            return
        recipient.acknowledged_at = utcnow()
        care_audit("care.handoff_acknowledged", identity)
        from services.notifications import emit

        emit(
            handoff.created_by,
            g.workspace_id,
            handoff.profile_id,
            "handoff",
            "handoff",
            identity,
            f"ack:{identity}:{current_user.id}",
            "acknowledged",
        )


def recipients_for(ids):
    if not ids:
        return {}
    rows = db.session.execute(
        select(Recipient, User.display_name, Member.status, Member.role)
        .join(User, User.id == Recipient.user_id)
        .outerjoin(
            Member,
            (Member.user_id == Recipient.user_id)
            & (Member.workspace_id == g.workspace_id),
        )
        .where(Recipient.handoff_id.in_(ids))
    ).all()
    result = {identity: [] for identity in ids}
    for row in rows:
        result[row[0].handoff_id].append(row)
    return result


def handoff_list(filters, page=1):
    require("care.view")
    if not 1 <= page <= 10000:
        abort(400)
    pending = exists().where(
        Recipient.handoff_id == Handoff.id, Recipient.acknowledged_at.is_(None)
    )
    query = select(Handoff).where(scope(Handoff, g.workspace_id))
    status = filters.get("status", "all")
    if status not in {"all", "pending", "acknowledged"}:
        abort(400)
    if status != "all":
        query = query.where(pending if status == "pending" else ~pending)
    if filters.get("inbox") == "1":
        query = query.where(
            exists().where(
                Recipient.handoff_id == Handoff.id,
                Recipient.user_id == current_user.id,
                Recipient.acknowledged_at.is_(None),
            )
        )
    tz = zone(current_app.config["APP_TIMEZONE"])
    if filters.get("from") and filters.get("to") and filters["from"] > filters["to"]:
        raise InvalidCare("The end date must follow the start date.")
    for name in ["from", "to"]:
        if filters.get(name):
            day = parse_date(filters[name])
            day = day + timedelta(days=1) if name == "to" else day
            stamp = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
            query = (
                query.where(Handoff.created_at >= stamp)
                if name == "from"
                else query.where(Handoff.created_at < stamp)
            )
    count = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(
        db.session.scalars(
            query.order_by(Handoff.created_at.desc(), Handoff.id)
            .offset((page - 1) * 20)
            .limit(20)
        )
    )
    return rows, recipients_for([h.id for h in rows]), count


def timeline(limit=20, page=1):
    require("care.view")
    if not 1 <= page <= 10000 or not 1 <= limit <= 20:
        abort(400)
    sources = [
        (
            Task,
            {
                "care.task_created": "Task created",
                "care.task_updated": "Task updated",
                "care.task_assigned": "Task assigned",
                "care.task_completed": "Task completed",
                "care.task_reopened": "Task reopened",
                "care.task_in_progress": "Task started",
                "care.task_canceled": "Task canceled",
            },
            "care.task_detail",
        ),
        (
            Handoff,
            {
                "care.handoff_created": "Handoff created",
                "care.handoff_acknowledged": "Handoff acknowledged",
            },
            "care.handoff_detail",
        ),
        (
            RoutineSession,
            {"routine.run_finished": "Guided routine completed"},
            "routines.routine_player",
        ),
        (
            Observation,
            {"observation.created": "Observation added"},
            "care.observation_detail",
        ),
        (
            CommunicationBoard,
            {"communication.board_saved": "Communication board updated"},
            "communication.board_view",
        ),
    ]
    terms = []
    mapping = {}
    for model, events, endpoint in sources:
        terms.append(
            AuditEvent.event_type.in_(events)
            & exists().where(
                cast(model.id, String) == AuditEvent.target_id,
                model.workspace_id == g.workspace_id,
                model.profile_id == g.profile_id,
            )
        )
        mapping.update({key: (label, endpoint) for key, label in events.items()})
    rows = db.session.execute(
        select(AuditEvent, User.display_name)
        .join(User, User.id == AuditEvent.actor_id)
        .where(AuditEvent.workspace_id == g.workspace_id, or_(*terms))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id)
        .offset((page - 1) * limit)
        .limit(limit + 1)
    ).all()
    return [
        (event, name, *mapping[event.event_type]) for event, name in rows[:limit]
    ], len(rows) > limit


def dashboard():
    require("care.view")
    tasks = list(
        db.session.scalars(
            select(Task)
            .where(
                scope(Task, g.workspace_id),
                Task.assigned_to == current_user.id,
                Task.status.in_(["todo", "in_progress"]),
            )
            .order_by(Task.due_at.asc().nullslast(), Task.created_at)
            .limit(3)
        )
    )
    handoffs, recipients, count = handoff_list(dict(inbox="1", status="pending"))
    activity, _ = timeline(3)
    return dict(
        my_care_tasks=tasks,
        pending_handoffs=handoffs[:3],
        pending_handoff_count=count,
        care_activity=activity,
    )
