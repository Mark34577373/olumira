"""Deterministic suggestions stay private until the author reviews and shares."""

from datetime import datetime, timedelta, timezone
from flask import abort, g, current_app
from flask_login import current_user
from sqlalchemy import select, func
from olumira.extensions import db
from olumira.models import (
    HandoffDraft,
    RoutineSession,
    CaregiverTask,
    Observation,
    User,
    utcnow,
)
from services.database import transaction
from services.workspaces import require, scope, care_audit
from services import (
    care_coordination as care,
    routine_scheduling as scheduling,
    calendar,
)
from services.communication import key, version


def find(identity):
    require("care.manage")
    draft = db.session.scalar(
        select(HandoffDraft)
        .where(
            HandoffDraft.id == identity,
            scope(HandoffDraft, g.workspace_id),
            HandoffDraft.created_by == current_user.id,
        )
        .execution_options(populate_existing=True)
    )
    if not draft:
        abort(404)
    return draft


def listing():
    require("care.manage")
    return list(
        db.session.scalars(
            select(HandoffDraft)
            .where(
                scope(HandoffDraft, g.workspace_id),
                HandoffDraft.created_by == current_user.id,
            )
            .order_by(HandoffDraft.updated_at.desc())
            .limit(50)
        )
    )


def period(values):
    tz = current_app.config["APP_TIMEZONE"]
    start = care.parse_due(values.get("start", ""), tz)
    end = care.parse_due(values.get("end", ""), tz)
    if not start or not end or not timedelta(0) < end - start <= timedelta(days=7):
        raise ValueError(
            "Choose a time range after the start and no longer than seven days."
        )
    return start, end


def generate(values, observation_ids, categories):
    require("care.manage")
    if values.get("profile_id", "") != (g.profile_id or ""):
        raise ValueError("Your profile changed. Reopen the generator.")
    recipient = care.validate_member(values.get("recipient"))
    if not recipient or recipient == current_user.id:
        raise ValueError("Choose another active caregiver.")
    start, end = period(values)
    if len(observation_ids) > 5 or len(set(observation_ids)) != len(observation_ids):
        raise ValueError("Select up to five different observations.")
    if not set(categories) <= {
        "completed",
        "unfinished",
        "tasks",
        "schedule",
        "observations",
    }:
        raise ValueError("Choose available summary sections.")
    parts = [
        f"Shift overview: {start.isoformat()} to {end.isoformat()}",
        f'Profile: {g.profile.display_name if g.profile else "Workspace-wide"}',
        f"Prepared by {current_user.display_name} for {db.session.get(User,recipient).display_name}",
    ]
    if "completed" in categories:
        rows = list(
            db.session.scalars(
                select(RoutineSession)
                .where(
                    scope(RoutineSession, g.workspace_id),
                    RoutineSession.status == "completed",
                    RoutineSession.completed_at >= start,
                    RoutineSession.completed_at < end,
                )
                .order_by(RoutineSession.completed_at)
                .limit(6)
            )
        )
        parts.append(
            "Completed routines:\n"
            + (
                "\n".join(
                    f"• {r.title[:80]} · {scheduling.aware(r.completed_at).isoformat()}"
                    for r in rows[:5]
                )
                or "None recorded in this period."
            )
            + ("\nMore available in routine history." if len(rows) > 5 else "")
        )
    local_start = start.astimezone(
        scheduling.zone(current_app.config["APP_TIMEZONE"])
    ).date()
    days = (
        end.astimezone(scheduling.zone(current_app.config["APP_TIMEZONE"])).date()
        - local_start
    ).days + 1
    schedule = (
        scheduling.calendar(local_start, days, current_app.config["APP_TIMEZONE"])
        if "unfinished" in categories
        else []
    )
    if "unfinished" in categories:
        unfinished = [
            item
            for item in schedule
            if start <= item["instant"] < end
            and item.get("status", "").lower() != "completed"
        ]
        parts.append(
            "Scheduled routines still to finish:\n"
            + (
                "\n".join("• " + item["title"][:80] for item in unfinished[:5])
                or "None in the selected period."
            )
        )
    if "tasks" in categories:
        tasks = list(
            db.session.scalars(
                select(CaregiverTask)
                .where(
                    scope(CaregiverTask, g.workspace_id),
                    CaregiverTask.status.in_(["todo", "in_progress"]),
                    CaregiverTask.created_at < end,
                )
                .order_by(CaregiverTask.due_at.asc().nullslast())
                .limit(5)
            )
        )
        lines = []
        for task in tasks:
            name = (
                db.session.get(User, task.assigned_to).display_name
                if task.assigned_to
                else "Unassigned"
            )
            lines.append(
                f'• {task.title[:80]} · {name[:40]} · {scheduling.aware(task.due_at).isoformat() if task.due_at else "No due date"} · {task.status}'
            )
        parts.append(
            "Currently open responsibilities (may predate this shift):\n"
            + ("\n".join(lines) or "None open.")
        )
    if "schedule" in categories:
        upcoming = calendar.events(
            end.astimezone(scheduling.zone(current_app.config["APP_TIMEZONE"])).date(),
            2,
            current_app.config["APP_TIMEZONE"],
        )
        rows = [
            item
            for item in upcoming
            if end <= item["instant"] < end + timedelta(days=1)
            and item["kind"] != "handoff"
        ][:5]
        parts.append(
            "Upcoming 24 hours:\n"
            + (
                "\n".join(
                    "• " + item["title"][:80] + " · " + item["instant"].isoformat()
                    for item in rows
                )
                or "None scheduled."
            )
        )
    if "observations" in categories:
        require("observations.view")
        selected = []
        for identity in observation_ids:
            observation = care.reference(Observation, identity, g.profile_id)
            if (
                observation.archived_at
                or not observation.observed_at
                or not start <= scheduling.aware(observation.observed_at) < end
            ):
                raise ValueError(
                    "Selected observations must have known times within the shift and be active."
                )
            selected.append(
                "• "
                + observation.activity[:80]
                + ": "
                + (observation.notes or "")[:100]
            )
        parts.append(
            "Explicitly selected observations:\n"
            + ("\n".join(selected) or "No observations selected for sharing.")
        )
    summary = "\n\n".join(parts)
    if len(summary) > 2000:
        raise ValueError(
            "The suggested summary is too long. Choose fewer sections or observations."
        )
    return dict(summary=summary, recipient=recipient, start=start, end=end)


def save(values, identity=None):
    summary = values.get("summary", "").strip()
    if not 1 <= len(summary) <= 2000:
        raise ValueError("Keep the handoff between 1 and 2,000 characters.")
    start, end = period(values)
    if values.get("state") not in {"draft", "ready"}:
        raise ValueError("Choose draft or ready.")
    with transaction():
        require("care.manage", lock=True)
        if values.get("profile_id", "") != (g.profile_id or ""):
            raise ValueError("Your profile changed. Reopen this draft.")
        recipient = care.validate_member(values.get("recipient"))
        if not recipient or recipient == current_user.id:
            raise ValueError("Choose another active caregiver.")
        draft = find(identity) if identity else None
        if draft:
            version(draft, values.get("version"))
            if draft.status == "shared":
                raise ValueError(
                    "Shared handoffs keep their original wording. Start a new draft."
                )
        else:
            identity = key(values.get("creation_key"))
            previous = db.session.get(HandoffDraft, identity)
            if previous:
                return find(identity).id
            if (
                db.session.scalar(
                    select(func.count())
                    .select_from(HandoffDraft)
                    .where(
                        scope(HandoffDraft, g.workspace_id),
                        HandoffDraft.created_by == current_user.id,
                    )
                )
                >= 1000
            ):
                raise ValueError(
                    "This profile has 1,000 private drafts. Review retention with your workspace owner."
                )
            draft = HandoffDraft(
                id=identity,
                workspace_id=g.workspace_id,
                profile_id=g.profile_id,
                created_by=current_user.id,
                version=0,
            )
        draft.summary = summary
        draft.recipient_id = recipient
        draft.period_start = start
        draft.period_end = end
        draft.status = values["state"]
        draft.version += 1
        draft.updated_at = utcnow()
        db.session.add(draft)
        care_audit("care.handoff_draft_saved", draft.id)
        return draft.id


def share(identity, expected):
    with transaction():
        require("care.manage", lock=True)
        draft = find(identity)
        if draft.shared_id:
            return draft.shared_id
        version(draft, expected)
        if draft.status != "ready":
            raise ValueError(
                "Review the final preview and mark this draft ready before sharing."
            )
        # Existing handoff service revalidates membership and stores an immutable shared copy.
        shared, profile = care.create_handoff(
            dict(
                summary=draft.summary,
                profile_id=draft.profile_id or "",
                recipient=draft.recipient_id,
                creation_key=draft.id,
            ),
            [],
        )
        draft.shared_id = shared
        draft.status = "shared"
        draft.version += 1
        care_audit("care.handoff_draft_shared", draft.id)
        return shared
