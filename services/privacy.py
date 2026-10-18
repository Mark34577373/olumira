"""Scoped JSON exports and explicit access-closure workflows.

Shared immutable history is retained. These workflows do not claim physical
record erasure or purge copies in operator-managed backups.
"""

import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from flask import g, abort
from flask_login import current_user
from sqlalchemy import select, update, delete, func, or_
from werkzeug.security import check_password_hash, generate_password_hash
from olumira.extensions import db
from olumira.models import (
    User,
    FamilyWorkspace,
    WorkspaceMembership,
    DataExport,
    DeletionRequest,
    Notification,
    NotificationPreference,
    AuthSession,
    AccountToken,
    EmailOutbox,
    WorkspaceInvitation,
    utcnow,
)
from services.database import transaction
from services.workspaces import require, lock_workspace, audit

MAX_ROWS = 10000
MAX_BYTES = 8 * 1024 * 1024
# Explicitly reviewed shared records. Personal preferences, account credentials,
# invitation tokens, email payloads and other recipients' inboxes are excluded.
SHARED = (
    "care_profiles",
    "routines",
    "observations",
    "routine_completions",
    "routine_completion_snapshots",
    "routine_steps",
    "routine_schedules",
    "routine_schedule_revisions",
    "routine_occurrences",
    "routine_sessions",
    "routine_session_steps",
    "routine_session_events",
    "routine_launch_requests",
    "communication_boards",
    "communication_cards",
    "saved_communication_phrases",
    "communication_preferences",
    "favorite_communication_cards",
    "favorite_communication_phrases",
    "care_plans",
    "care_goals",
    "care_plan_routines",
    "care_plan_boards",
    "care_plan_tasks",
    "caregiver_tasks",
    "caregiver_handoffs",
    "handoff_recipients",
    "handoff_tasks",
    "calendar_events",
    "audit_events",
)
PERSONAL = (
    "handoff_drafts",
    "user_preferences",
    "dashboard_preferences",
    "reminder_preferences",
    "notification_preferences",
    "resource_bookmarks",
    "onboarding_states",
    "notifications",
)


def reauthenticate(password):
    if (
        not isinstance(password, str)
        or len(password) > 128
        or not check_password_hash(current_user.password_hash, password)
    ):
        raise ValueError("Your current password could not be verified.")


def request_export(values):
    scope = values.get("scope")
    if scope not in ("personal", "workspace"):
        raise ValueError("Choose a supported export scope.")
    with transaction():
        if scope == "workspace" or g.workspace_id:
            require(
                "workspace.manage" if scope == "workspace" else "workspace.view",
                lock=True,
            )
        reauthenticate(values.get("current_password", ""))
        if (values.get("scope_workspace") or None) != g.workspace_id:
            raise ValueError("Your workspace changed. Reload before exporting.")
        raw = secrets.token_urlsafe(32)
        row = DataExport(
            id=uuid.uuid4().hex,
            user_id=current_user.id,
            workspace_id=g.workspace_id,
            scope=scope,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=int(time.time()) + 300,
        )
        db.session.add(row)
        if g.workspace_id:
            audit("privacy.export_requested", g.workspace_id, current_user.id, row.id)
    return raw


def _table_query(name, wid, visited=None):
    table = db.metadata.tables[name]
    if "workspace_id" in table.c:
        return select(table).where(table.c.workspace_id == wid)
    # Children are selected through a reviewed shared parent, never by an
    # unscoped owner/user identifier. Handle composite FK columns individually.
    visited = set(visited or ()) | {name}
    for column in table.c:
        for fk in column.foreign_keys:
            parent = fk.column.table.name
            if parent in SHARED and parent not in visited:
                parent_query = _table_query(parent, wid, visited)
                if parent_query is not None:
                    ids = parent_query.with_only_columns(fk.column)
                    return select(table).where(column.in_(ids))
    raise ValueError("An export relationship needs operator review.")


def _serialize(query, remaining):
    rows = []
    size = 0
    for row in db.session.execute(
        query.limit(remaining + 1).execution_options(yield_per=100)
    ).mappings():
        if len(rows) >= remaining:
            raise ValueError(
                "This export exceeds 10,000 records. Ask your operator for a scoped database export."
            )
        value = dict(row)
        size += len(json.dumps(value, default=_json_default).encode())
        if size > MAX_BYTES:
            raise ValueError(
                "This export exceeds 8 MiB. Ask your operator for a scoped database export."
            )
        rows.append(value)
    return rows


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("Unsupported export value")


def download(raw):
    if not isinstance(raw, str) or len(raw) != 43:
        abort(404)
    with transaction():
        if g.workspace_id:
            require("workspace.view", lock=True)
        # User lock makes single-use personal grants safe even without a workspace.
        db.session.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(updated_at=User.updated_at)
        )
        grant = db.session.scalar(
            select(DataExport)
            .where(
                DataExport.user_id == current_user.id,
                DataExport.token_hash == hashlib.sha256(raw.encode()).hexdigest(),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        moment = int(time.time())
        if (
            not grant
            or grant.workspace_id != g.workspace_id
            or grant.expires_at <= moment
            or grant.consumed_at is not None
        ):
            abort(404)
        if grant.scope == "workspace":
            require("workspace.manage")
        payload = {
            "format": "olumira-json-1",
            "scope": grant.scope,
            "generated_at": utcnow().isoformat(),
            "exclusions": [
                "passwords",
                "session handles",
                "email payloads",
                "invitation tokens",
                "database backups",
            ],
            "records": {},
        }
        remaining = MAX_ROWS
        if grant.scope == "personal":
            payload["account"] = {
                field: getattr(current_user, field)
                for field in (
                    "id",
                    "email",
                    "display_name",
                    "email_verified",
                    "created_at",
                )
            }
            payload["scope_explanation"] = (
                "Your account and personal preferences across workspaces. Shared care records and other caregivers are excluded."
            )
            names = PERSONAL
        else:
            payload["workspace"] = {
                "id": g.workspace_id,
                "name": db.session.get(FamilyWorkspace, g.workspace_id).name,
            }
            payload["scope_explanation"] = (
                "All care profiles and shared care records in this workspace. Account secrets and individual personal preferences are excluded."
            )
            names = SHARED
        for name in names:
            table = db.metadata.tables[name]
            query = (
                select(table).where(
                    (
                        table.c.created_by
                        if name == "handoff_drafts"
                        else table.c.user_id
                    )
                    == current_user.id
                )
                if grant.scope == "personal"
                else _table_query(name, g.workspace_id)
            )
            if name == "handoff_drafts":
                active = (
                    select(WorkspaceMembership.workspace_id)
                    .join(
                        FamilyWorkspace,
                        FamilyWorkspace.id == WorkspaceMembership.workspace_id,
                    )
                    .where(
                        WorkspaceMembership.user_id == current_user.id,
                        WorkspaceMembership.status == "active",
                        FamilyWorkspace.closed_at.is_(None),
                    )
                )
                query = select(table).where(
                    table.c.created_by == current_user.id,
                    table.c.workspace_id.in_(active),
                )
            rows = _serialize(query, remaining)
            remaining -= len(rows)
            payload["records"][name] = rows
            # Stop before retaining an unbounded aggregate payload.
            if len(json.dumps(payload, default=_json_default).encode()) > MAX_BYTES:
                raise ValueError(
                    "This export exceeds 8 MiB. Ask your operator for a scoped database export."
                )
        encoded = json.dumps(payload, default=_json_default, ensure_ascii=False).encode(
            "utf-8"
        )
        grant.consumed_at = moment
        if g.workspace_id:
            audit(
                "privacy.export_downloaded", g.workspace_id, current_user.id, grant.id
            )
        return encoded, "olumira-" + grant.scope + "-export.json"


def _cancel_invitations(wid, moment):
    ids = select(WorkspaceInvitation.id).where(WorkspaceInvitation.workspace_id == wid)
    db.session.execute(
        update(EmailOutbox)
        .where(EmailOutbox.invitation_id.in_(ids), EmailOutbox.delivered_at.is_(None))
        .values(cancelled_at=moment)
    )
    db.session.execute(
        update(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.workspace_id == wid,
            WorkspaceInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=moment)
    )


def close_workspace(values):
    with transaction():
        require("workspace.manage", lock=True)
        reauthenticate(values.get("current_password", ""))
        if (
            values.get("confirm") != "CLOSE WORKSPACE"
            or values.get("scope_workspace") != g.workspace_id
        ):
            raise ValueError("Type CLOSE WORKSPACE and check the selected workspace.")
        wid = g.workspace_id
        moment = int(time.time())
        workspace = db.session.get(FamilyWorkspace, wid)
        audit("privacy.workspace_closed", wid, current_user.id, wid)
        db.session.add(
            DeletionRequest(
                id=uuid.uuid4().hex,
                user_id=current_user.id,
                workspace_id=wid,
                scope="workspace",
                status="access_closed_history_retained",
            )
        )
        workspace.closed_at = utcnow()
        _cancel_invitations(wid, moment)
        db.session.execute(
            update(WorkspaceMembership)
            .where(WorkspaceMembership.workspace_id == wid)
            .values(status="revoked")
        )
        db.session.execute(delete(DataExport).where(DataExport.workspace_id == wid))


def transfer_ownership(values):
    with transaction():
        require("workspace.manage", lock=True)
        reauthenticate(values.get("current_password", ""))
        if values.get("scope_workspace") != g.workspace_id:
            raise ValueError("Your workspace changed. Reload.")
        member = db.session.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == g.workspace_id,
                WorkspaceMembership.user_id == values.get("successor"),
                WorkspaceMembership.status == "active",
            )
        )
        if not member or member.user_id == current_user.id:
            raise ValueError("Choose another active workspace member.")
        successor = db.session.scalar(
            select(User)
            .where(User.id == member.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            not successor
            or successor.closed_at is not None
            or not successor.email_verified
        ):
            raise ValueError("Choose a verified active member.")
        member.role = "owner"
        audit("privacy.owner_added", g.workspace_id, current_user.id, member.id)


def close_account(values):
    # Take workspace locks in sorted order, then user lock, matching membership
    # writers. Recheck all owners under those locks before changing anything.
    with transaction():
        memberships = list(
            db.session.scalars(
                select(WorkspaceMembership)
                .join(FamilyWorkspace)
                .where(
                    WorkspaceMembership.user_id == current_user.id,
                    WorkspaceMembership.status == "active",
                    FamilyWorkspace.closed_at.is_(None),
                )
                .order_by(WorkspaceMembership.workspace_id)
            )
        )
        locked_workspaces = {member.workspace_id for member in memberships}
        for member in memberships:
            lock_workspace(member.workspace_id)
        user = db.session.scalar(
            select(User)
            .where(User.id == current_user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        reauthenticate(values.get("current_password", ""))
        if values.get("confirm") != "DELETE MY ACCOUNT":
            raise ValueError("Type DELETE MY ACCOUNT to confirm account closure.")
        db.session.expire_all()
        memberships = list(
            db.session.scalars(
                select(WorkspaceMembership)
                .join(FamilyWorkspace)
                .where(
                    WorkspaceMembership.user_id == user.id,
                    WorkspaceMembership.status == "active",
                    FamilyWorkspace.closed_at.is_(None),
                )
            )
        )
        if {member.workspace_id for member in memberships} != locked_workspaces:
            raise ValueError(
                "Your memberships changed during this request. Reload Privacy and retry account deletion."
            )
        for member in memberships:
            if member.role == "owner" and not db.session.scalar(
                select(WorkspaceMembership.id).where(
                    WorkspaceMembership.workspace_id == member.workspace_id,
                    WorkspaceMembership.role == "owner",
                    WorkspaceMembership.status == "active",
                    WorkspaceMembership.user_id != user.id,
                )
            ):
                raise ValueError(
                    "You are the sole owner of a workspace. Add another owner or close that workspace before deleting your account."
                )
        moment = int(time.time())
        for member in memberships:
            audit("privacy.account_closed", member.workspace_id, user.id, user.id)
            member.status = "revoked"
        db.session.add(
            DeletionRequest(
                id=uuid.uuid4().hex,
                user_id=user.id,
                workspace_id=g.workspace_id,
                scope="personal",
                status="anonymized_history_retained",
            )
        )
        user.closed_at = utcnow()
        user.email = "closed-" + user.id + "@deleted.invalid"
        user.display_name = "Deleted caregiver"
        user.pending_email = None
        user.email_verified = False
        user.password_hash = generate_password_hash(secrets.token_urlsafe(64))
        user.auth_version += 1
        db.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id)
            .values(revoked_at=moment)
        )
        db.session.execute(
            update(AccountToken)
            .where(AccountToken.user_id == user.id, AccountToken.used_at.is_(None))
            .values(used_at=moment)
        )
        db.session.execute(
            update(EmailOutbox)
            .where(EmailOutbox.user_id == user.id, EmailOutbox.delivered_at.is_(None))
            .values(cancelled_at=moment, encrypted_payload="")
        )
        for name in PERSONAL + ("data_exports",):
            table = db.metadata.tables[name]
            db.session.execute(
                delete(table).where(
                    (
                        table.c.created_by
                        if name == "handoff_drafts"
                        else table.c.user_id
                    )
                    == user.id
                )
            )


def cleanup(now=None):
    """Remove only expired download grants and old read/dismissed inbox rows."""
    now = now or utcnow()
    moment = int(now.timestamp())
    removed = 0
    with transaction():
        removed += db.session.execute(
            delete(DataExport).where(DataExport.expires_at <= moment)
        ).rowcount
        # Iterate stable preference keys; default members retain for 90 days.
        after = ""
        while True:
            rows = list(
                db.session.scalars(
                    select(Notification)
                    .where(
                        Notification.id > after,
                        or_(
                            Notification.read_at.is_not(None),
                            Notification.dismissed_at.is_not(None),
                        ),
                    )
                    .order_by(Notification.id)
                    .limit(500)
                )
            )
            if not rows:
                break
            for row in rows:
                after = row.id
                pref = db.session.get(
                    NotificationPreference, (row.user_id, row.workspace_id)
                )
                days = pref.retention_days if pref else 90
                timestamp = row.dismissed_at or row.read_at
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                if timestamp <= now - timedelta(days=days):
                    db.session.delete(row)
                    removed += 1
    return removed
