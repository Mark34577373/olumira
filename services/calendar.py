"""Unified bounded calendar using the existing routine recurrence/DST rules."""

import uuid
from datetime import datetime, date, time, timedelta, timezone
from types import SimpleNamespace
from flask import g, abort, url_for, current_app
from flask_login import current_user
from sqlalchemy import select, or_, and_, func
from olumira.extensions import db
from olumira.models import (
    CalendarEvent as Event,
    ReminderPreference as Preference,
    CaregiverTask as Task,
    CaregiverHandoff as Handoff,
    WorkspaceMembership,
    User,
    utcnow,
)
from services import routine_scheduling as scheduling
from services.workspaces import scope, require, care_audit
from services.database import transaction

TYPES = ("routine", "task", "event", "handoff")
VIEWS = ("month", "week", "day", "agenda")


class CalendarConflict(ValueError):
    pass


def context(values):
    if values.get("scope_workspace") != g.workspace_id or values.get(
        "profile_id", ""
    ) != (g.profile_id or ""):
        raise CalendarConflict("Your workspace or profile changed. Reopen the form.")


def find(identity):
    require("calendar.view")
    row = db.session.scalar(
        select(Event)
        .where(Event.id == identity, scope(Event, g.owner_id))
        .execution_options(populate_existing=True)
    )
    if not row:
        abort(404)
    return row


def members():
    return db.session.execute(
        select(User.id, User.display_name)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
        .where(
            WorkspaceMembership.workspace_id == g.workspace_id,
            WorkspaceMembership.status == "active",
            WorkspaceMembership.role.in_(["owner", "caregiver"]),
        )
        .order_by(User.display_name, User.id)
    ).all()


def validate(values):
    clean = {
        k: (values.get(k) or "").strip()
        for k in [
            "title",
            "description",
            "start_date",
            "local_time",
            "end_date",
            "end_time",
            "timezone",
            "frequency",
            "repeat_until",
            "assigned_to",
        ]
    }
    if (
        not clean["title"]
        or len(clean["title"]) > 120
        or len(clean["description"]) > 2000
    ):
        raise ValueError(
            "Enter a title up to 120 characters and a description up to 2,000."
        )
    start = scheduling.parse_date(clean["start_date"])
    end = scheduling.parse_date(clean["end_date"])
    tz = str(scheduling.zone(clean["timezone"]))
    all_day = values.get("all_day") in ["on", "1", True]
    if all_day:
        clean["local_time"] = clean["end_time"] = "00:00"
    import re

    if any(
        not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clean[k])
        for k in ["local_time", "end_time"]
    ):
        raise ValueError("Use a valid hour and minute.")
    a = scheduling.local_instant(start, clean["local_time"], tz)
    b = scheduling.local_instant(end, clean["end_time"], tz)
    if a is None or b is None:
        raise ValueError(
            "This local clock time does not exist because of daylight saving time."
        )
    if end < start or (end - start).days > 30 or b <= a:
        raise ValueError(
            "End must follow start by at most 30 days. All-day end dates are exclusive (the day after the final day)."
        )
    if clean["frequency"] not in ["once", "daily", "weekly", "weekdays"]:
        raise ValueError("Choose a supported recurrence.")
    weekdays = (
        values.getlist("weekdays")
        if hasattr(values, "getlist")
        else values.get("weekdays", [])
    )
    if not isinstance(weekdays, list) or any(
        str(d) not in list("0123456") for d in weekdays
    ):
        raise ValueError("Choose valid weekdays.")
    if clean["frequency"] == "weekdays" and not weekdays:
        raise ValueError("Select at least one weekday.")
    if clean["repeat_until"] and scheduling.parse_date(clean["repeat_until"]) < start:
        raise ValueError("Repeat-until date must be on or after the first event date.")
    if clean["assigned_to"] and clean["assigned_to"] not in {
        uid for uid, _ in members()
    }:
        raise ValueError("Select an active caregiver in this workspace.")
    clean.update(
        timezone=tz,
        all_day=all_day,
        assigned_to=clean["assigned_to"] or None,
        weekdays=(
            ",".join(sorted(set(weekdays)))
            if clean["frequency"] == "weekdays"
            else str(start.weekday()) if clean["frequency"] == "weekly" else ""
        ),
        repeat_until=clean["repeat_until"] or None,
    )
    return clean


def save(values, identity=None):
    require("calendar.manage", lock=True)
    with transaction():
        context(values)
        row = find(identity) if identity else None
        if row and str(row.version) != str(values.get("version")):
            raise CalendarConflict(
                "This event changed. Reload before editing the series."
            )
        cleaned = validate(values)
        if row and row.status != "active":
            raise CalendarConflict("Restore this series before editing.")
        if not row:
            identity = values.get("creation_key", "")
            if (
                not isinstance(identity, str)
                or len(identity) != 32
                or any(c not in "0123456789abcdef" for c in identity)
            ):
                raise ValueError("Reload the form before creating an event.")
            existing = db.session.get(Event, identity)
            if existing:
                if (
                    existing.workspace_id != g.workspace_id
                    or existing.profile_id != g.profile_id
                    or existing.created_by != current_user.id
                ):
                    abort(404)
                return existing.id
            count = db.session.scalar(
                select(func.count()).select_from(Event).where(scope(Event, g.owner_id))
            )
            if count >= 500:
                raise ValueError(
                    "This profile has reached 500 custom event series. Reuse or edit an existing event."
                )
            row = Event(
                id=identity,
                workspace_id=g.workspace_id,
                profile_id=g.profile_id,
                created_by=current_user.id,
                status="active",
                version=1,
            )
            db.session.add(row)
        else:
            row.version += 1
        for key, value in cleaned.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        db.session.flush()
        care_audit("calendar.created" if not identity else "calendar.saved", row.id)
        return row.id


def status(identity, values, desired):
    require("calendar.manage", lock=True)
    if desired not in ["active", "canceled", "archived"]:
        abort(404)
    with transaction():
        context(values)
        row = find(identity)
        if str(row.version) != str(values.get("version")):
            raise CalendarConflict("This event changed. Reload before updating it.")
        if row.status != desired:
            row.status = desired
            row.version += 1
            row.updated_at = utcnow()
            care_audit("calendar." + desired, row.id)


def window(values):
    tz = str(
        scheduling.zone(values.get("timezone") or current_app.config["APP_TIMEZONE"])
    )
    day = scheduling.parse_date(
        values.get("date") or datetime.now(scheduling.zone(tz)).date().isoformat()
    )
    if not 1901 <= day.year <= 9996:
        raise ValueError("Choose a calendar year between 1901 and 9996.")
    view = values.get("view", "month")
    if view not in VIEWS:
        raise ValueError("Choose month, week, day or agenda.")
    if view == "month":
        first = day.replace(day=1)
        start = first - timedelta(days=first.weekday())
        days = 42
        previous = (first - timedelta(days=1)).replace(day=1)
        following = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    else:
        days = {"week": 7, "day": 1, "agenda": 14}[view]
        start = day - timedelta(days=day.weekday()) if view == "week" else day
        previous = day - timedelta(days=days)
        following = day + timedelta(days=days)
    return dict(
        date=day,
        start=start,
        days=days,
        view=view,
        timezone=tz,
        previous=previous,
        following=following,
    )


def events(start, days, tz, kind="", include_inactive=False, assigned_only=False):
    require("calendar.view")
    if not 1 <= days <= 42 or kind not in ("",) + TYPES:
        raise ValueError("Choose a bounded calendar period and event type.")
    zone = scheduling.zone(tz)
    lower = datetime.combine(start, time.min, zone).astimezone(timezone.utc)
    upper = datetime.combine(start + timedelta(days=days), time.min, zone).astimezone(
        timezone.utc
    )
    result = []

    def add(identity, title, instant, end, kind, url, status="active", all_day=False):
        if len(result) >= 3000:
            raise ValueError(
                "More than 3,000 events match. Choose a shorter view or event type."
            )
        result.append(
            dict(
                id=str(identity),
                title=title,
                instant=instant,
                end=end,
                display=instant.astimezone(zone),
                kind=kind,
                url=url,
                status=status,
                all_day=all_day,
            )
        )

    if kind in ["", "routine"]:
        for row in scheduling.calendar(start, days, tz):
            add(
                row["id"],
                row["title"],
                row["instant"],
                row["instant"],
                "routine",
                (
                    url_for("routines.routine_player", session_id=row["session_id"])
                    if row["session_id"]
                    else url_for(
                        "routines.routine_calendar",
                        view="day",
                        date=row["display"].date().isoformat(),
                        timezone=tz,
                    )
                ),
                row["status"],
            )
    if kind in ["", "task"]:
        query = select(Task).where(
            scope(Task, g.owner_id),
            Task.due_at >= lower,
            Task.due_at < upper,
            Task.status != "canceled",
        )
        if assigned_only:
            query = query.where(Task.assigned_to == current_user.id)
        for row in db.session.scalars(query.limit(3001)):
            add(
                row.id,
                row.title,
                scheduling.aware(row.due_at),
                scheduling.aware(row.due_at),
                "task",
                url_for("care.task_detail", task_id=row.id),
                row.status,
            )
    if kind in ["", "handoff"]:
        for row in db.session.scalars(
            select(Handoff).where(
                scope(Handoff, g.owner_id),
                Handoff.created_at >= lower,
                Handoff.created_at < upper,
            )
        ):
            add(
                row.id,
                "Caregiver handoff",
                scheduling.aware(row.created_at),
                scheduling.aware(row.created_at),
                "handoff",
                url_for("care.handoff_detail", handoff_id=row.id),
                "Recorded",
            )
    if kind in ["", "event"]:
        query = select(Event).where(
            scope(Event, g.owner_id),
            Event.start_date <= (upper + timedelta(days=1)).date().isoformat(),
            or_(
                Event.frequency != "once",
                Event.end_date >= (lower - timedelta(days=1)).date().isoformat(),
            ),
        )
        if not include_inactive:
            query = query.where(Event.status == "active")
        for row in db.session.scalars(query):
            duration = (
                date.fromisoformat(row.end_date) - date.fromisoformat(row.start_date)
            ).days
            rule = SimpleNamespace(
                start_date=row.start_date,
                end_date=row.repeat_until
                or (row.start_date if row.frequency == "once" else None),
                frequency=row.frequency,
                weekdays=row.weekdays,
                local_time=row.local_time,
                timezone=row.timezone,
                valid_from=datetime(1900, 1, 1, tzinfo=timezone.utc),
                valid_until=None,
            )
            day = lower.astimezone(scheduling.zone(row.timezone)).date() - timedelta(
                days=duration + 1
            )
            last = upper.astimezone(scheduling.zone(row.timezone)).date()
            while day <= last:
                instant = scheduling.candidate(rule, day)
                end = (
                    scheduling.local_instant(
                        day + timedelta(days=duration), row.end_time, row.timezone
                    )
                    if instant
                    else None
                )
                if instant and end and instant < upper and end > lower:
                    add(
                        row.id + ":" + day.isoformat(),
                        row.title,
                        instant,
                        end,
                        "event",
                        url_for("calendar.detail", identity=row.id),
                        row.status,
                        row.all_day,
                    )
                day += timedelta(days=1)
    result.sort(key=lambda r: (r["instant"], r["kind"], r["id"]))
    if len(result) > 3000:
        raise ValueError(
            "More than 3,000 events match this period. Select a shorter view or an event type."
        )
    return result


def preferences():
    require("calendar.view")
    return db.session.get(
        Preference, (current_user.id, g.workspace_id, g.profile_id or "")
    ) or SimpleNamespace(
        enabled=True, lead_minutes=60, categories="routine,task,event", version=0
    )


def save_preferences(values):
    require("calendar.view", lock=True)
    with transaction():
        context(values)
        row = preferences()
        if str(row.version) != str(values.get("version")):
            raise CalendarConflict(
                "Reminder preferences changed. Reload before saving."
            )
        try:
            lead = int(values.get("lead_minutes", ""))
        except ValueError:
            raise ValueError("Choose a supported reminder lead time.")
        categories = (
            values.getlist("categories")
            if hasattr(values, "getlist")
            else values.get("categories", [])
        )
        if lead not in [0, 15, 60, 1440] or any(k not in TYPES[:3] for k in categories):
            raise ValueError("Choose valid reminder options.")
        if row.version == 0:
            row = Preference(
                user_id=current_user.id,
                workspace_id=g.workspace_id,
                context_key=g.profile_id or "",
                profile_id=g.profile_id,
                version=0,
            )
            db.session.add(row)
        row.enabled = values.get("enabled") == "on"
        row.lead_minutes = lead
        row.categories = ",".join(k for k in TYPES if k in categories)
        row.version += 1


def reminders(display_zone=None):
    pref = preferences()
    if not pref.enabled:
        return []
    now = utcnow()
    tz = display_zone or current_app.config["APP_TIMEZONE"]
    day = now.astimezone(scheduling.zone(tz)).date()
    rows = events(day - timedelta(days=7), 9, tz, assigned_only=True)
    return [
        row
        for row in rows
        if row["kind"] in pref.categories.split(",")
        and row["status"].lower() not in ["completed", "canceled", "archived"]
        and row["instant"] <= now + timedelta(minutes=pref.lead_minutes)
        and (
            row["kind"] == "task"
            or row["end"] >= now
            or row["instant"] >= now - timedelta(hours=24)
        )
    ][:20]
