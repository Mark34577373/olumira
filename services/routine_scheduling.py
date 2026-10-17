"""Bounded, timezone-aware recurrence. Materialize only when a run is launched."""

import hashlib
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import abort, g
from flask_login import current_user
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import (
    Routine,
    RoutineSchedule as Schedule,
    RoutineScheduleRevision as Revision,
    RoutineOccurrence as Occurrence,
    RoutineSession,
    RoutineSessionStep,
    utcnow,
)
from services.database import transaction
from services.workspaces import require, scope, care_audit
from services import routine_builder as builder


class InvalidSchedule(ValueError):
    pass


class ScheduleConflict(InvalidSchedule):
    pass


def aware(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def parse_date(value):
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value or not 1900 <= result.year <= 9998:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise InvalidSchedule("Choose a valid date between 1900 and 9998.") from None


def zone(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise InvalidSchedule("Choose an IANA timezone, such as America/Chicago.")
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise InvalidSchedule(
            "Choose an IANA timezone, such as America/Chicago."
        ) from None


def local_instant(day, clock, tz):
    """First fold for repeated times; nonexistent spring-forward times are skipped."""
    local = datetime.combine(day, time.fromisoformat(clock), tzinfo=zone(tz)).replace(
        fold=0
    )
    instant = local.astimezone(timezone.utc)
    return (
        instant
        if instant.astimezone(zone(tz)).replace(tzinfo=None)
        == local.replace(tzinfo=None)
        else None
    )


def values_from_form(form):
    values = {
        k: form.get(k, "").strip()
        for k in (
            "timezone",
            "local_time",
            "frequency",
            "start_date",
            "end_date",
            "version",
        )
    }
    values["weekdays"] = form.getlist("weekdays")
    return values


def clean_values(values):
    tz = str(values.get("timezone", "")).strip()
    tzinfo = zone(tz)
    clock = str(values.get("local_time", ""))
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock):
        raise InvalidSchedule("Choose a time using hours and minutes.")
    start = parse_date(values.get("start_date"))
    end = parse_date(values["end_date"]) if values.get("end_date") else None
    frequency = values.get("frequency")
    if frequency not in {"once", "daily", "weekdays", "weekly"}:
        raise InvalidSchedule("Choose one of the available repeat options.")
    if end and end < start:
        raise InvalidSchedule("The end date must be on or after the start date.")
    raw = values.get("weekdays", [])
    if not isinstance(raw, list) or any(str(d) not in list("0123456") for d in raw):
        raise InvalidSchedule("Choose valid weekdays.")
    days = (
        sorted(set(int(d) for d in raw))
        if frequency == "weekdays"
        else [start.weekday()] if frequency == "weekly" else []
    )
    if frequency == "weekdays" and not days:
        raise InvalidSchedule("Choose at least one weekday.")
    now = utcnow()
    if end and end < now.astimezone(tzinfo).date():
        raise InvalidSchedule("The end date cannot be in the past.")
    if frequency == "once":
        instant = local_instant(start, clock, tz)
        if instant is None:
            raise InvalidSchedule(
                "That local time does not exist during the daylight-saving change. Choose another time."
            )
        if instant <= now:
            raise InvalidSchedule(
                "Choose a future date and time for a one-time routine."
            )
        end = start
    return dict(
        timezone=tz,
        local_time=clock,
        frequency=frequency,
        weekdays=",".join(map(str, days)),
        start_date=start.isoformat(),
        end_date=end.isoformat() if end else None,
    )


def revision_values(revision):
    return {
        key: getattr(revision, key)
        for key in (
            "timezone",
            "local_time",
            "frequency",
            "weekdays",
            "start_date",
            "end_date",
        )
    }


def find(schedule_id, permission="routines.view"):
    require(permission)
    result = db.session.scalar(
        select(Schedule)
        .where(Schedule.id == schedule_id, scope(Schedule, g.workspace_id))
        .execution_options(populate_existing=True)
    )
    if not result:
        abort(404)
    return result


def current_revision(schedule):
    return db.session.scalar(
        select(Revision)
        .where(
            Revision.schedule_id == schedule.id, Revision.number == schedule.revision
        )
        .execution_options(populate_existing=True)
    )


def check_version(obj, expected):
    if str(expected) != str(obj.version):
        raise ScheduleConflict(
            "Another caregiver changed this record. Review the latest saved version before trying again."
        )


def close_revision(schedule, instant):
    revision = current_revision(schedule)
    if revision.valid_until is None:
        revision.valid_until = instant


def add_revision(schedule, values, instant):
    revision = Revision(
        id=uuid.uuid4().hex,
        schedule_id=schedule.id,
        number=schedule.revision,
        valid_from=instant,
        **values
    )
    db.session.add(revision)
    return revision


def save(routine_id, values, schedule_id=None):
    with transaction():
        require("routines.edit", lock=True)
        routine = builder.find(routine_id, "routines.edit")
        if routine.archived_at:
            raise InvalidSchedule("Restore this routine before scheduling it.")
        clean = clean_values(values)
        schedule = find(schedule_id, "routines.edit") if schedule_id else None
        if schedule and schedule.routine_id != routine.id:
            abort(404)
        if schedule:
            check_version(schedule, values.get("version"))
            if schedule.state == "ended":
                raise InvalidSchedule(
                    "This schedule has ended. Create a new schedule instead."
                )
        # Serialize duplicate detection under the workspace lock, including paused rules.
        others = db.session.execute(
            select(Schedule, Revision)
            .join(
                Revision,
                (Revision.schedule_id == Schedule.id)
                & (Revision.number == Schedule.revision),
            )
            .where(Schedule.routine_id == routine.id, Schedule.state != "ended")
        ).all()
        if any(s.id != schedule_id and revision_values(r) == clean for s, r in others):
            raise InvalidSchedule(
                "This routine already has that schedule. Edit or resume the existing one."
            )
        instant = utcnow()
        if schedule:
            close_revision(schedule, instant)
            schedule.revision += 1
            schedule.version += 1
        else:
            if len(others) >= 12:
                raise InvalidSchedule(
                    "A routine can have up to 12 active or paused schedules. End one before adding another."
                )
            schedule = Schedule(
                id=uuid.uuid4().hex,
                routine_id=routine.id,
                workspace_id=g.workspace_id,
                profile_id=g.profile_id,
                created_by=current_user.id,
                state="active",
                version=1,
                revision=1,
            )
            db.session.add(schedule)
            db.session.flush()
        revision = add_revision(schedule, clean, instant)
        if schedule.state == "paused":
            revision.valid_until = instant
        care_audit("routine.schedule_saved", schedule.id)
        result = schedule.id
    return result


def change_state(schedule_id, action, version):
    if action not in {"pause", "resume", "end"}:
        abort(400)
    with transaction():
        require("routines.edit", lock=True)
        schedule = find(schedule_id, "routines.edit")
        check_version(schedule, version)
        if schedule.state == "ended":
            raise InvalidSchedule(
                "This schedule has ended. Create a new schedule instead."
            )
        routine = builder.find(schedule.routine_id, "routines.edit")
        instant = utcnow()
        if action == "resume":
            if routine.archived_at:
                raise InvalidSchedule(
                    "Restore the routine before resuming its schedule."
                )
            if schedule.state == "active":
                return
            clean = revision_values(current_revision(schedule))
            # Revalidate end dates and one-time rules when resuming an old schedule.
            clean_values(
                dict(
                    clean,
                    weekdays=clean["weekdays"].split(",") if clean["weekdays"] else [],
                )
            )
            schedule.revision += 1
            add_revision(schedule, clean, instant)
            schedule.state = "active"
        else:
            close_revision(schedule, instant)
            schedule.state = "paused" if action == "pause" else "ended"
        schedule.version += 1
        care_audit("routine.schedule_" + action, schedule.id)


def pause_for_archive(routine_id):
    """Called inside the already locked parent archive transaction; never commits."""
    for schedule in db.session.scalars(
        select(Schedule).where(
            Schedule.routine_id == routine_id, Schedule.state == "active"
        )
    ):
        close_revision(schedule, utcnow())
        schedule.state = "paused"
        schedule.version += 1


def schedule_list(routine_id=None):
    query = (
        select(Schedule, Revision, Routine.name)
        .join(
            Revision,
            (Revision.schedule_id == Schedule.id)
            & (Revision.number == Schedule.revision),
        )
        .join(Routine, Routine.id == Schedule.routine_id)
        .where(scope(Schedule, g.workspace_id))
    )
    if routine_id is not None:
        query = query.where(Schedule.routine_id == routine_id)
    return db.session.execute(
        query.order_by(Schedule.created_at.desc()).limit(480)
    ).all()


def candidate(revision, day):
    start = parse_date(revision.start_date)
    if day < start or revision.end_date and day > parse_date(revision.end_date):
        return None
    if revision.frequency == "once" and day != start:
        return None
    if revision.frequency in {"weekly", "weekdays"} and str(
        day.weekday()
    ) not in revision.weekdays.split(","):
        return None
    instant = local_instant(day, revision.local_time, revision.timezone)
    if (
        instant is None
        or instant < aware(revision.valid_from)
        or revision.valid_until
        and instant >= aware(revision.valid_until)
    ):
        return None
    return instant


def occurrence_id(revision_id, day):
    return hashlib.sha256(
        (revision_id + ":" + day.isoformat()).encode("ascii")
    ).hexdigest()


def calendar(start, days, display_zone):
    require("routines.view")
    if not 1 <= days <= 42:
        raise InvalidSchedule("Choose a window of up to 42 days.")
    tz = zone(display_zone)
    if start.year >= 9998:
        raise InvalidSchedule("Choose an earlier calendar date.")
    lower = datetime.combine(start, time.min, tzinfo=tz).astimezone(timezone.utc)
    upper = datetime.combine(
        start + timedelta(days=days), time.min, tzinfo=tz
    ).astimezone(timezone.utc)
    rows = db.session.execute(
        select(Schedule, Revision, Routine)
        .join(Revision, Revision.schedule_id == Schedule.id)
        .join(Routine, Routine.id == Schedule.routine_id)
        .where(
            scope(Schedule, g.workspace_id),
            Revision.valid_from < upper,
            (Revision.valid_until.is_(None)) | (Revision.valid_until > lower),
        )
    ).all()
    items = {}
    # Convert window boundaries into each rule's local calendar; at most 16 days.
    for schedule, revision, routine in rows:
        day = lower.astimezone(zone(revision.timezone)).date()
        last = (
            (upper - timedelta(microseconds=1))
            .astimezone(zone(revision.timezone))
            .date()
        )
        while day <= last:
            instant = candidate(revision, day)
            if (
                instant
                and lower <= instant < upper
                and (not routine.archived_at or instant < aware(routine.archived_at))
            ):
                key = occurrence_id(revision.id, day)
                items[key] = dict(
                    id=key,
                    revision_id=revision.id,
                    local_date=day.isoformat(),
                    title=routine.name,
                    routine_id=routine.id,
                    instant=instant,
                    display=instant.astimezone(tz),
                    timezone=revision.timezone,
                    local_time=revision.local_time,
                    session_id=None,
                    status="Scheduled",
                    completed=0,
                    total=0,
                    overlap=False,
                    archived=bool(routine.archived_at),
                    available=schedule.state == "active"
                    and revision.number == schedule.revision
                    and not routine.archived_at
                    and utcnow().astimezone(zone(revision.timezone)).date()
                    - timedelta(days=7)
                    <= day
                    <= utcnow().astimezone(zone(revision.timezone)).date()
                    + timedelta(days=14),
                )
            day += timedelta(days=1)
    persisted = db.session.execute(
        select(Occurrence, RoutineSession)
        .outerjoin(RoutineSession, RoutineSession.occurrence_id == Occurrence.id)
        .where(
            scope(Occurrence, g.workspace_id),
            Occurrence.scheduled_at >= lower,
            Occurrence.scheduled_at < upper,
        )
    ).all()
    session_ids = [s.id for _, s in persisted if s]
    counts = {}
    if session_ids:
        counts = {
            sid: (total, done)
            for sid, total, done in db.session.execute(
                select(
                    RoutineSessionStep.session_id,
                    func.count(),
                    func.count(RoutineSessionStep.completed_at),
                )
                .where(RoutineSessionStep.session_id.in_(session_ids))
                .group_by(RoutineSessionStep.session_id)
            )
        }
    for occ, run in persisted:
        if not run:
            continue
        total, done = counts.get(run.id, (0, 0))
        instant = aware(occ.scheduled_at)
        items[occ.id] = dict(
            id=occ.id,
            revision_id=occ.revision_id,
            local_date=occ.local_date,
            title=run.title,
            routine_id=occ.routine_id,
            instant=instant,
            display=instant.astimezone(tz),
            timezone=occ.timezone,
            local_time=occ.local_time,
            session_id=run.id,
            status=run.status.title(),
            completed=done,
            total=total,
            overlap=False,
            archived=False,
            available=False,
        )
    result = sorted(items.values(), key=lambda item: (item["instant"], item["id"]))
    for a, b in zip(result, result[1:]):
        if a["instant"] == b["instant"]:
            a["overlap"] = b["overlap"] = True
    return result


def materialize(revision_id, day_value):
    """Requires the launch caller's workspace lock and transaction."""
    day = parse_date(day_value)
    revision = db.session.get(Revision, revision_id)
    if not revision:
        abort(404)
    schedule = find(revision.schedule_id, "routines.complete")
    key = occurrence_id(revision.id, day)
    existing = db.session.get(Occurrence, key)
    if existing:
        return existing
    routine = builder.find(schedule.routine_id, "routines.complete")
    instant = candidate(revision, day)
    if (
        not instant
        or routine.archived_at
        or schedule.state != "active"
        or schedule.revision != revision.number
    ):
        raise InvalidSchedule(
            "This occurrence is no longer available. Open the latest schedule."
        )
    # Prevent arbitrary unbounded record creation outside the visible calendar window.
    today = utcnow().astimezone(zone(revision.timezone)).date()
    if not today - timedelta(days=7) <= day <= today + timedelta(days=14):
        raise InvalidSchedule(
            "Launch a scheduled routine within seven days before or fourteen days after today."
        )
    result = Occurrence(
        id=key,
        revision_id=revision.id,
        routine_id=routine.id,
        workspace_id=g.workspace_id,
        profile_id=g.profile_id,
        scheduled_at=instant,
        local_date=day_value,
        local_time=revision.local_time,
        timezone=revision.timezone,
    )
    db.session.add(result)
    db.session.flush()
    return result


def upcoming(display_zone):
    tz = zone(display_zone)
    now = utcnow()
    return [
        item
        for item in calendar(now.astimezone(tz).date(), 14, display_zone)
        if item["instant"] >= now and item["status"] != "Completed"
    ][:5]
