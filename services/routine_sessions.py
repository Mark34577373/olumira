"""Shared runs with frozen content, idempotent intents and optimistic versions."""

import re
import uuid
from datetime import datetime, time, timedelta, timezone
from flask import abort, g
from flask_login import current_user
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import (
    RoutineSession as Session,
    RoutineSessionStep as Step,
    RoutineSessionEvent as Event,
    RoutineLaunchRequest as Launch,
    User,
    utcnow,
)
from services.database import transaction
from services.workspaces import require, scope, care_audit
from services import routine_builder as builder, routine_scheduling as scheduling


class RunConflict(ValueError):
    pass


def nonce(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{32}", value):
        abort(400, description="Reload this page before trying again.")
    return value


def find(session_id, permission="routines.view"):
    require(permission)
    result = db.session.scalar(
        select(Session)
        .where(Session.id == session_id, scope(Session, g.workspace_id))
        .execution_options(populate_existing=True)
    )
    if not result:
        abort(404)
    return result


def steps_for(session_id):
    return list(
        db.session.scalars(
            select(Step)
            .where(Step.session_id == session_id)
            .order_by(Step.position)
            .execution_options(populate_existing=True)
        )
    )


def event(run, action, step=None, event_id=None):
    db.session.add(
        Event(
            id=event_id or uuid.uuid4().hex,
            session_id=run.id,
            step_id=step.id if step else None,
            actor_id=current_user.id,
            action=action,
        )
    )
    care_audit("routine.run_" + action, run.id)


def start(routine_id, key, revision_id=None, local_date=None):
    nonce(key)
    with transaction():
        require("routines.complete", lock=True)
        routine = builder.find(routine_id, "routines.complete")
        previous = db.session.get(Launch, key)
        if previous:
            if (
                previous.workspace_id != g.workspace_id
                or previous.actor_id != current_user.id
                or previous.routine_id != routine_id
            ):
                abort(404)
            old = find(previous.session_id, "routines.complete")
            if revision_id:
                wanted = scheduling.occurrence_id(
                    revision_id, scheduling.parse_date(local_date)
                )
                if old.occurrence_id != wanted:
                    abort(400)
            elif old.occurrence_id:
                abort(400)
            return old.id
        occurrence = (
            scheduling.materialize(revision_id, local_date) if revision_id else None
        )
        if occurrence and occurrence.routine_id != routine.id:
            abort(404)
        if occurrence:
            run = db.session.scalar(
                select(Session).where(Session.occurrence_id == occurrence.id)
            )
        else:
            run = db.session.scalar(
                select(Session).where(Session.active_key == str(routine.id))
            )
        if not run:
            if routine.archived_at:
                raise RunConflict(
                    "This routine is archived. Restore it before starting a new run."
                )
            templates = builder.steps_for(routine.id)
            if not templates:
                raise RunConflict("Add a step before starting this routine.")
            run = Session(
                id=uuid.uuid4().hex,
                routine_id=routine.id,
                workspace_id=g.workspace_id,
                profile_id=g.profile_id,
                occurrence_id=occurrence.id if occurrence else None,
                active_key=None if occurrence else str(routine.id),
                title=routine.name,
                description=routine.description,
                icon=routine.icon,
                color=routine.color,
                profile_name=g.profile.display_name if g.profile else g.workspace.name,
                routine_version=routine.version,
                started_by=current_user.id,
                status="active",
                version=1,
            )
            db.session.add(run)
            db.session.flush()
            for template in templates:
                db.session.add(
                    Step(
                        id=uuid.uuid4().hex,
                        session_id=run.id,
                        title=template.title,
                        description=template.description,
                        icon=template.icon,
                        position=template.position,
                        timer_seconds=template.timer_seconds,
                    )
                )
            event(run, "started")
        db.session.flush()
        db.session.add(
            Launch(
                id=key,
                workspace_id=g.workspace_id,
                actor_id=current_user.id,
                routine_id=routine_id,
                session_id=run.id,
            )
        )
        result = run.id
    return result


def mutate(session_id, action, version, action_id, step_id=None):
    nonce(action_id)
    if action not in {"complete", "undo", "pause", "resume"}:
        abort(400)
    with transaction():
        require("routines.complete", lock=True)
        run = find(session_id, "routines.complete")
        # Replayed forms return current state without applying an older intent twice.
        prior = db.session.get(Event, action_id)
        if prior:
            if (prior.session_id, prior.actor_id, prior.action, prior.step_id) != (
                run.id,
                current_user.id,
                action,
                step_id,
            ):
                abort(400)
            return run.id
        if str(version) != str(run.version):
            raise RunConflict(
                "Another caregiver updated this routine. The latest saved progress is shown; review it before trying again."
            )
        if run.status == "completed":
            raise RunConflict(
                "This completed run is preserved in history. Start a new run from the routine library."
            )
        if action in {"complete", "undo"}:
            if run.status != "active":
                raise RunConflict("Resume this routine before changing its steps.")
            step = db.session.scalar(
                select(Step)
                .where(Step.id == step_id, Step.session_id == run.id)
                .execution_options(populate_existing=True)
            )
            if not step:
                abort(404)
            desired = action == "complete"
            if bool(step.completed_at) == desired:
                # A fresh desired-state request is a harmless no-op, not a toggle.
                event(run, action, step, action_id)
                return run.id
            step.completed_at = utcnow() if desired else None
            step.completed_by = current_user.id if desired else None
            event(run, action, step, action_id)
            db.session.flush()
            remaining = db.session.scalar(
                select(func.count())
                .select_from(Step)
                .where(Step.session_id == run.id, Step.completed_at.is_(None))
            )
            if not remaining:
                run.status = "completed"
                run.completed_at = utcnow()
                run.active_key = None
                event(run, "finished")
        else:
            run.status = "paused" if action == "pause" else "active"
            run.paused_at = utcnow() if action == "pause" else None
            event(run, action, event_id=action_id)
        run.version += 1
        result = run.id
    return result


def history(filters, page=1):
    require("routines.view")
    if not 1 <= page <= 10000:
        abort(400)
    query = select(Session).where(scope(Session, g.workspace_id))
    status = filters.get("status", "")
    if status:
        if status not in {"active", "paused", "completed"}:
            abort(400)
        query = query.where(Session.status == status)
    routine_id = filters.get("routine", "")
    if routine_id:
        try:
            query = query.where(Session.routine_id == int(routine_id))
        except (ValueError, TypeError):
            abort(400)
    tz = scheduling.zone(filters.get("timezone", "UTC"))
    for field, comparison in [("from", "start"), ("to", "end")]:
        if filters.get(field):
            day = scheduling.parse_date(filters[field])
            if comparison == "end":
                day += timedelta(days=1)
            instant = datetime.combine(day, time.min, tzinfo=tz).astimezone(
                timezone.utc
            )
            query = (
                query.where(Session.started_at >= instant)
                if comparison == "start"
                else query.where(Session.started_at < instant)
            )
    if filters.get("from") and filters.get("to") and filters["from"] > filters["to"]:
        raise scheduling.InvalidSchedule("The end date must follow the start date.")
    count = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(
        db.session.scalars(
            query.order_by(Session.started_at.desc(), Session.id)
            .offset((page - 1) * 20)
            .limit(20)
        )
    )
    ids = [r.id for r in rows]
    counts = (
        {
            sid: (total, done)
            for sid, total, done in db.session.execute(
                select(Step.session_id, func.count(), func.count(Step.completed_at))
                .where(Step.session_id.in_(ids))
                .group_by(Step.session_id)
            )
        }
        if ids
        else {}
    )
    return rows, counts, count


def activity(session_id):
    return db.session.execute(
        select(Event, User.display_name)
        .join(User, User.id == Event.actor_id)
        .where(Event.session_id == session_id)
        .order_by(Event.created_at.desc(), Event.id)
        .limit(100)
    ).all()


def today_summary(display_zone):
    tz = scheduling.zone(display_zone)
    day = utcnow().astimezone(tz).date()
    low = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
    high = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(
        timezone.utc
    )
    completed = db.session.scalar(
        select(func.count())
        .select_from(Session)
        .where(
            scope(Session, g.workspace_id),
            Session.completed_at >= low,
            Session.completed_at < high,
        )
    )
    unfinished = list(
        db.session.scalars(
            select(Session)
            .where(scope(Session, g.workspace_id), Session.status != "completed")
            .order_by(Session.started_at.desc())
            .limit(5)
        )
    )
    return completed, unfinished
