"""Scoped journal validation and pagination over the original observation table."""

from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import g, abort, current_app
from flask_login import current_user
from sqlalchemy import select, func, or_, and_, case
from olumira.extensions import db
from olumira.models import Observation, RoutineSession, CaregiverTask, User, utcnow
from services.workspaces import scope, require, care_audit
from services.database import transaction

CATEGORIES = (
    "Daily activities",
    "Communication",
    "Routines",
    "Learning",
    "Social interaction",
    "Preferences",
    "Achievements",
    "General notes",
)
PAGE_SIZE = 20


class Conflict(ValueError):
    pass


def zone(value=None):
    value = value or current_app.config["APP_TIMEZONE"]
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Choose a valid IANA timezone, such as America/Chicago.")


def aware(value):
    return (
        value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
    )


def stamp(value, tz=None):
    return (
        aware(value).astimezone(zone(tz)).strftime("%b %d, %Y at %I:%M %p %Z")
        if value
        else "Unknown (legacy record)"
    )


def find(identity):
    require("observations.view")
    row = db.session.scalar(
        select(Observation)
        .where(Observation.id == identity, scope(Observation, g.owner_id))
        .execution_options(populate_existing=True)
    )
    if not row:
        abort(404)
    return row


def clean(values):
    result = {
        k: (values.get(k) or "").strip()
        for k in ["activity", "date", "notes", "mood", "tags", "category"]
    }
    result["category"] = result["category"] or "General notes"
    limits = dict(activity=120, date=10, notes=2000, mood=20, tags=120, category=60)
    if not result["activity"] or any(len(result[k]) > v for k, v in limits.items()):
        raise ValueError(
            "Enter a title up to 120 characters, notes up to 2,000, category up to 60, mood up to 20 and tags up to 120."
        )
    try:
        day = date.fromisoformat(result["date"])
        if day.isoformat() != result["date"] or not 1900 <= day.year <= 9998:
            raise ValueError()
    except ValueError:
        raise ValueError("Enter a valid observation date.")
    tags = list(
        dict.fromkeys(
            t.strip().casefold() for t in result["tags"].split(",") if t.strip()
        )
    )
    if len(tags) > 10 or any(len(t) > 30 or any(ord(c) < 32 for c in t) for t in tags):
        raise ValueError("Use up to 10 comma-separated tags, each up to 30 characters.")
    result["tags"] = ", ".join(tags)
    result["timezone"] = str(zone(values.get("timezone")))
    clock = (values.get("time") or "").strip()
    result["observed_at"] = None
    if clock:
        try:
            parsed = time.fromisoformat(clock)
            if parsed.tzinfo is not None:
                raise ValueError()
            local = datetime.combine(day, parsed).replace(
                tzinfo=zone(result["timezone"]), fold=0
            )
            if local.astimezone(timezone.utc).astimezone(local.tzinfo).replace(
                tzinfo=None
            ) != local.replace(tzinfo=None):
                raise ValueError()
            result["observed_at"] = local.astimezone(timezone.utc)
        except ValueError:
            raise ValueError(
                "Enter a valid local time. This clock time may not exist because of daylight saving time."
            )
    for key, model in [("session_id", RoutineSession), ("task_id", CaregiverTask)]:
        identity = (values.get(key) or "").strip()
        if identity and not db.session.scalar(
            select(model.id).where(model.id == identity, scope(model, g.owner_id))
        ):
            raise ValueError(
                "Choose related records from this workspace and care profile."
            )
        result[key] = identity or None
    return result


def save(values, identity=None):
    require("observations.edit" if identity else "observations.create", lock=True)
    with transaction():
        row = find(identity) if identity else None
        if row:
            if str(row.version) != str(values.get("version", "")):
                raise Conflict(
                    "Another caregiver changed this entry. Reopen it before saving; your entered text remains below."
                )
            if row.archived_at:
                raise Conflict("Restore this archived entry before editing.")
        if values.get(
            "scope_workspace", g.workspace_id
        ) != g.workspace_id or values.get("profile_id", g.profile_id or "") != (
            g.profile_id or ""
        ):
            raise Conflict(
                "Your workspace or profile changed. Reopen the form before saving."
            )
        cleaned = clean(values)
        if not row:
            row = Observation(
                owner_id=g.owner_id,
                workspace_id=g.workspace_id,
                profile_id=g.profile_id,
                author_id=current_user.id,
                created_at=utcnow(),
            )
            db.session.add(row)
        else:
            row.version += 1
        for key, value in cleaned.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        db.session.flush()
        care_audit("observation.updated" if identity else "observation.created", row.id)
        return row.id


def archive(identity, version, desired):
    require("observations.edit", lock=True)
    with transaction():
        row = find(identity)
        if str(row.version) != str(version):
            raise Conflict(
                "This entry changed. Reload before updating its archive status."
            )
        if bool(row.archived_at) != desired:
            row.archived_at = utcnow() if desired else None
            row.version += 1
            row.updated_at = utcnow()
            care_audit(
                "observation.archived" if desired else "observation.restored", row.id
            )


def references(row=None):
    choices = dict(
        sessions=list(
            db.session.scalars(
                select(RoutineSession)
                .where(scope(RoutineSession, g.owner_id))
                .order_by(RoutineSession.started_at.desc(), RoutineSession.id)
                .limit(100)
            )
        ),
        tasks=list(
            db.session.scalars(
                select(CaregiverTask)
                .where(scope(CaregiverTask, g.owner_id))
                .order_by(CaregiverTask.created_at.desc(), CaregiverTask.id)
                .limit(100)
            )
        ),
    )
    if row:
        for key, model, identity in [
            ("sessions", RoutineSession, row.session_id),
            ("tasks", CaregiverTask, row.task_id),
        ]:
            if identity and not any(item.id == identity for item in choices[key]):
                linked = db.session.scalar(
                    select(model).where(model.id == identity, scope(model, g.owner_id))
                )
                if linked:
                    choices[key].append(linked)
    return choices


def names(rows):
    ids = {r.author_id for r in rows if r.author_id}
    return (
        dict(
            db.session.execute(
                select(User.id, User.display_name).where(User.id.in_(ids))
            ).all()
        )
        if ids
        else {}
    )


def listing(filters, page=1):
    require("observations.view")
    if not 1 <= page <= 10000:
        raise ValueError("Choose a valid page.")
    query = select(Observation).where(scope(Observation, g.owner_id))
    status = filters.get("status", "active") or "active"
    if status not in ["active", "archived", "all"]:
        raise ValueError("Choose an archive status.")
    if status != "all":
        query = query.where(
            Observation.archived_at.is_not(None)
            if status == "archived"
            else Observation.archived_at.is_(None)
        )
    for key in ["q", "category", "tag", "author"]:
        if len(filters.get(key, "") or "") > 120:
            raise ValueError("Shorten the search or filter.")
    if filters.get("q"):
        text = filters["q"]
        query = query.where(
            or_(
                *[
                    column.icontains(text, autoescape=True)
                    for column in [
                        Observation.activity,
                        Observation.notes,
                        Observation.tags,
                        Observation.category,
                    ]
                ]
            )
        )
    if filters.get("category"):
        query = query.where(Observation.category == filters["category"])
    if filters.get("tag"):
        # Comma-delimited canonical tags, matched as a full tag, not as a substring.
        token = filters["tag"].strip().casefold()
        query = query.where(
            or_(
                func.lower(Observation.tags) == token,
                func.lower(Observation.tags).startswith(token + ", ", autoescape=True),
                func.lower(Observation.tags).endswith(", " + token, autoescape=True),
                func.lower(Observation.tags).contains(
                    ", " + token + ", ", autoescape=True
                ),
            )
        )
    if filters.get("author"):
        query = query.where(Observation.author_id == filters["author"])
    period = filters.get("period", "")
    if period not in ["", "today", "7", "30", "custom"]:
        raise ValueError("Choose a valid date range.")
    tz = zone(filters.get("timezone"))
    start = filters.get("from", "")
    end = filters.get("to", "")
    if period in ["today", "7", "30"]:
        last = datetime.now(tz).date()
        first = last - timedelta(days=(1 if period == "today" else int(period)) - 1)
    elif start or end:
        try:
            first = date.fromisoformat(start)
            last = date.fromisoformat(end)
        except ValueError:
            raise ValueError("Enter both start and end dates.")
    else:
        first = last = None
    if first:
        if (
            first > last
            or (last - first).days > 365
            or first.year < 1900
            or last.year > 9998
        ):
            raise ValueError("Choose an inclusive date range of up to 366 days.")
        lower = datetime.combine(first, time.min, tz).astimezone(timezone.utc)
        upper = datetime.combine(last + timedelta(days=1), time.min, tz).astimezone(
            timezone.utc
        )
        query = query.where(
            or_(
                and_(Observation.observed_at >= lower, Observation.observed_at < upper),
                and_(
                    Observation.observed_at.is_(None),
                    Observation.date >= first.isoformat(),
                    Observation.date <= last.isoformat(),
                ),
            )
        )
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    # Legacy records retain their real date without fabricating a time or author.
    rows = list(
        db.session.scalars(
            query.order_by(*chronology())
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        )
    )
    return rows, total


def sa_timestamp_text():
    from sqlalchemy import cast, String

    return cast(Observation.observed_at, String)


def options():
    base = scope(Observation, g.owner_id)
    categories = list(
        db.session.scalars(
            select(Observation.category)
            .where(base)
            .distinct()
            .order_by(Observation.category)
        )
    )
    authors = db.session.execute(
        select(User.id, User.display_name)
        .join(Observation, Observation.author_id == User.id)
        .where(base)
        .distinct()
        .order_by(User.display_name, User.id)
    ).all()
    return sorted(set(CATEGORIES) | set(categories)), authors


def chronology():
    day = case(
        (Observation.observed_at.is_not(None), func.substr(sa_timestamp_text(), 1, 10)),
        else_=Observation.date,
    )
    return (
        day.desc(),
        Observation.observed_at.desc().nullslast(),
        Observation.id.desc(),
    )
