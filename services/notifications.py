"""Private in-app events. All creation joins the caller's business transaction."""

import hashlib
import uuid
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from flask import g, abort, session, url_for
from flask_login import current_user
from sqlalchemy import select, func, update, or_
from olumira.extensions import db
from olumira.models import (
    Notification as Notice,
    NotificationPreference as Preference,
    WorkspaceMembership,
    CareProfile,
    User,
    CaregiverTask,
    CaregiverHandoff,
    CalendarEvent,
    utcnow,
)
from services.database import transaction
from services.workspaces import require, membership, lock_workspace

CATEGORIES = {
    "task": "Caregiver tasks",
    "handoff": "Handoff updates",
    "routine": "Routine reminders",
    "event": "Calendar reminders",
}
TITLES = {
    "assigned": "A caregiver task was assigned to you",
    "handoff": "A handoff is ready for your review",
    "acknowledged": "A handoff was acknowledged",
    "task": "A caregiver task is due",
    "routine": "A scheduled routine is approaching",
    "event": "A calendar event is approaching",
}


def preferences():
    require("workspace.view")
    return db.session.get(
        Preference, (current_user.id, g.workspace_id)
    ) or SimpleNamespace(categories=",".join(CATEGORIES), retention_days=90, version=0)


def save_preferences(values):
    with transaction():
        require("workspace.view", lock=True)
        if values.get("scope_workspace") != g.workspace_id:
            raise ValueError("Your workspace changed. Reload settings.")
        pref = preferences()
        categories = values.getlist("categories")
        if any(c not in CATEGORIES for c in categories) or values.get(
            "retention_days"
        ) not in ("30", "90", "180"):
            raise ValueError("Choose valid notification options.")
        if values.get("version") != str(pref.version):
            raise ValueError("Settings changed. Reload before saving.")
        if not pref.version:
            pref = Preference(
                user_id=current_user.id, workspace_id=g.workspace_id, version=0
            )
            db.session.add(pref)
        pref.categories = ",".join(c for c in CATEGORIES if c in categories)
        pref.retention_days = int(values["retention_days"])
        pref.version += 1


def emit(
    user_id,
    workspace_id,
    profile_id,
    category,
    entity_type,
    entity_id,
    event_key,
    title_key,
):
    # Caller locks workspace before reaching this service. Check current permissions
    # and profile provenance again, including after a role change.
    member = membership(workspace_id, user_id)
    user = db.session.get(User, user_id)
    if not member or not user or not user.email_verified:
        return False
    if category == "handoff" and member.role == "viewer":
        return False
    if profile_id and not db.session.scalar(
        select(CareProfile.id).where(
            CareProfile.id == profile_id, CareProfile.workspace_id == workspace_id
        )
    ):
        return False
    pref = db.session.get(Preference, (user_id, workspace_id))
    if pref and category not in pref.categories.split(","):
        return False
    key = hashlib.sha256(f"{user_id}:{workspace_id}:{event_key}".encode()).hexdigest()
    if db.session.scalar(select(Notice.id).where(Notice.dedup_key == key)):
        return False
    db.session.add(
        Notice(
            id=uuid.uuid4().hex,
            user_id=user_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            category=category,
            entity_type=entity_type,
            entity_id=str(entity_id),
            title=TITLES[title_key],
            dedup_key=key,
        )
    )
    db.session.flush()
    return True


def query():
    require("workspace.view")
    allowed = list(CATEGORIES)
    if require("workspace.view").role == "viewer":
        allowed.remove("handoff")
    return select(Notice).where(
        Notice.user_id == current_user.id,
        Notice.workspace_id == g.workspace_id,
        Notice.category.in_(allowed),
    )


def inbox(category="", state="all", page=1):
    if (
        category
        and category not in CATEGORIES
        or state not in ("all", "unread", "read")
        or not 1 <= page <= 10000
    ):
        raise ValueError("Choose valid notification filters.")
    q = query().where(Notice.dismissed_at.is_(None))
    if category:
        q = q.where(Notice.category == category)
    if state == "unread":
        q = q.where(Notice.read_at.is_(None))
    if state == "read":
        q = q.where(Notice.read_at.is_not(None))
    return list(
        db.session.scalars(
            q.order_by(Notice.created_at.desc(), Notice.id)
            .offset((page - 1) * 20)
            .limit(21)
        )
    )


def unread_count():
    q = (
        query()
        .where(Notice.read_at.is_(None), Notice.dismissed_at.is_(None))
        .subquery()
    )
    return db.session.scalar(select(func.count()).select_from(q))


def action(identity, desired):
    if desired not in ("read", "unread", "dismiss", "open", "all-read"):
        abort(400)
    with transaction():
        require("workspace.view", lock=True)
        if desired == "all-read":
            ids = (
                query()
                .with_only_columns(Notice.id)
                .where(Notice.read_at.is_(None), Notice.dismissed_at.is_(None))
            )
            db.session.execute(
                update(Notice).where(Notice.id.in_(ids)).values(read_at=utcnow())
            )
            return None
        row = db.session.scalar(query().where(Notice.id == identity))
        if not row:
            abort(404)
        destination = None
        if desired == "open":
            # Never trust a stored URL. Revalidate entity scope and fresh membership.
            model = {
                "task": CaregiverTask,
                "handoff": CaregiverHandoff,
                "event": CalendarEvent,
            }.get(row.entity_type)
            if model:
                entity = db.session.get(model, row.entity_id)
                if not entity or (entity.workspace_id, entity.profile_id) != (
                    g.workspace_id,
                    row.profile_id,
                ):
                    abort(404)
            elif row.entity_type != "routine":
                abort(404)
            session["profile_id"] = row.profile_id
            destination = {
                "task": lambda: url_for("care.task_detail", task_id=row.entity_id),
                "handoff": lambda: url_for(
                    "care.handoff_detail", handoff_id=row.entity_id
                ),
                "event": lambda: url_for("calendar.detail", identity=row.entity_id),
                "routine": lambda: url_for("calendar.calendar", view="agenda"),
            }[row.entity_type]()
        if desired in ("read", "open"):
            row.read_at = row.read_at or utcnow()
        if desired == "unread":
            row.read_at = None
        if desired == "dismiss":
            row.dismissed_at = row.dismissed_at or utcnow()
        return destination


def process_reminders(app, now=None):
    """Restart-safe scheduled command; each member/profile is its own transaction.

    Recompute occurrences using the same DST and revision rules as calendar.
    No page loads or process-local timers are required. Repeated runs insert once.
    A 24h catch-up window tolerates missed cron runs without sending old history.
    """
    from services import calendar
    from services.workspaces import resolve_context
    from services.routine_scheduling import aware

    now = now or datetime.now(timezone.utc)
    total = 0
    after = ""
    while True:
        pairs = list(
            db.session.execute(
                select(
                    WorkspaceMembership.id,
                    WorkspaceMembership.user_id,
                    WorkspaceMembership.workspace_id,
                )
                .where(
                    WorkspaceMembership.status == "active",
                    WorkspaceMembership.id > after,
                )
                .order_by(WorkspaceMembership.id)
                .limit(100)
            )
        )
        if not pairs:
            break
        for mid, uid, wid in pairs:
            after = mid
            profiles = [None] + list(
                db.session.scalars(
                    select(CareProfile.id).where(CareProfile.workspace_id == wid)
                )
            )
            for pid in profiles:
                with app.test_request_context("/calendar"):
                    g._login_user = db.session.get(User, uid)
                    if not g._login_user or not g._login_user.email_verified:
                        continue
                    session["workspace_id"] = wid
                    session["profile_id"] = pid
                    resolve_context()
                    if g.workspace_id != wid:
                        continue
                    with transaction():
                        lock_workspace(wid)
                        if not membership(wid, uid):
                            continue
                        pref = calendar.preferences()
                        # A bounded three-day UTC window includes local dates around DST.
                        rows = calendar.events(
                            (now - timedelta(days=1)).date(),
                            4,
                            "UTC",
                            assigned_only=True,
                        )
                        valid_keys = set()
                        for row in rows:
                            if not pref.enabled:
                                continue
                            if (
                                not row["reminder_eligible"]
                                or row["kind"] not in pref.categories.split(",")
                                or row["status"].casefold()
                                in ("completed", "canceled", "archived")
                            ):
                                continue
                            instant = aware(row["instant"])
                            trigger = instant - timedelta(minutes=pref.lead_minutes)
                            if not now - timedelta(hours=24) <= trigger <= now:
                                continue
                            entity = (
                                row["id"].split(":", 1)[0]
                                if row["kind"] == "event"
                                else row["id"]
                            )
                            # Time is part of the key: an edited start time creates one
                            # new reminder; recurring occurrences each have their own.
                            key = f"reminder:{row['kind']}:{row['id']}:{instant.isoformat()}"
                            valid_keys.add(
                                hashlib.sha256(
                                    f"{uid}:{wid}:{key}".encode()
                                ).hexdigest()
                            )
                            total += emit(
                                uid,
                                wid,
                                pid,
                                row["kind"],
                                row["kind"],
                                entity,
                                key,
                                row["kind"],
                            )
                        # Superseded, canceled, completed, or disabled reminders must
                        # not stay actionable as if they were still upcoming.
                        pending = select(Notice).where(
                            Notice.user_id == uid,
                            Notice.workspace_id == wid,
                            Notice.profile_id == pid,
                            Notice.entity_type.in_(["task", "event", "routine"]),
                            Notice.dismissed_at.is_(None),
                        )
                        for notice in db.session.scalars(pending):
                            if (
                                notice.title
                                in (TITLES["task"], TITLES["event"], TITLES["routine"])
                                and notice.dedup_key not in valid_keys
                            ):
                                notice.dismissed_at = now
    return total
