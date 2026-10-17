"""Central membership authorization. Session IDs select context, never grant access."""

import uuid
from flask import abort, g, has_request_context, session
from flask_login import current_user
from sqlalchemy import select, update
from olumira.extensions import db
from olumira.models import (
    FamilyWorkspace,
    WorkspaceMembership,
    CareProfile,
    AuditEvent,
    Owner,
)
from services.database import transaction, today_string

READ = frozenset(
    {
        "workspace.view",
        "members.view",
        "profiles.view",
        "routines.view",
        "observations.view",
        "communication.view",
        "care.view",
        "analytics.view",
    }
)
WRITE = frozenset(
    {
        "profiles.create",
        "profiles.edit",
        "routines.create",
        "routines.edit",
        "routines.complete",
        "observations.create",
        "observations.edit",
        "communication.manage",
        "care.manage",
        "reports.generate",
        "care.acknowledge",
    }
)
PERMISSIONS = {
    "viewer": READ,
    "caregiver": READ | WRITE,
    "owner": READ
    | WRITE
    | {"workspace.manage", "members.invite", "members.manage", "audit.view"},
}


def audit(event_type, workspace_id, actor_id, target_id=None):
    db.session.add(
        AuditEvent(
            id=uuid.uuid4().hex,
            workspace_id=workspace_id,
            actor_id=actor_id,
            event_type=event_type,
            target_id=target_id,
        )
    )


def memberships(user_id):
    return db.session.execute(
        select(WorkspaceMembership, FamilyWorkspace)
        .join(FamilyWorkspace)
        .where(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.status == "active",
        )
        .order_by(FamilyWorkspace.created_at, FamilyWorkspace.id)
    ).all()


def lock_workspace(workspace_id):
    # A write lock also serializes SQLite membership/invitation mutations. PostgreSQL
    # locks this same row, establishing a consistent workspace -> membership order.
    db.session.execute(
        update(FamilyWorkspace)
        .where(FamilyWorkspace.id == workspace_id)
        .values(updated_at=FamilyWorkspace.updated_at)
    )


def membership(workspace_id, user_id):
    return db.session.scalar(
        select(WorkspaceMembership)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.status == "active",
        )
        .execution_options(populate_existing=True)
    )


def can(permission):
    member = getattr(g, "membership", None)
    return bool(member and permission in PERMISSIONS.get(member.role, frozenset()))


def require(permission, workspace_id=None, *, lock=False):
    if not current_user.is_authenticated or not current_user.email_verified:
        abort(403)
    workspace_id = workspace_id or getattr(g, "workspace_id", None)
    if not workspace_id:
        abort(404)
    if lock:
        lock_workspace(workspace_id)
    member = membership(workspace_id, current_user.id)
    if not member:
        abort(404)
    if permission not in PERMISSIONS.get(member.role, frozenset()):
        abort(403)
    return member


def resolve_context():
    choices = memberships(current_user.id)
    g.workspace_choices = choices
    chosen = session.get("workspace_id")
    pair = next((pair for pair in choices if pair[1].id == chosen), None)
    if pair is None:
        session.pop("profile_id", None)
        pair = choices[0] if choices else None
    g.membership, g.workspace = pair if pair else (None, None)
    g.workspace_id = g.workspace.id if g.workspace else None
    g.owner_id = (
        g.workspace_id
    )  # compatibility argument; HTTP services use explicit scope below.
    if g.workspace_id:
        session["workspace_id"] = g.workspace_id
    else:
        session.pop("workspace_id", None)
    g.profiles = (
        list(
            db.session.scalars(
                select(CareProfile)
                .where(CareProfile.workspace_id == g.workspace_id)
                .order_by(CareProfile.display_name)
            )
        )
        if pair
        else []
    )
    selected = session.get("profile_id")
    g.profile = next(
        (profile for profile in g.profiles if profile.id == selected), None
    )
    g.profile_id = g.profile.id if g.profile else None
    if not g.profile:
        session.pop("profile_id", None)


def create_workspace(user_id, name, *, workspace_id=None):
    name = (name or "").strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError("Use a workspace name of 1–80 characters.")
    workspace_id = workspace_id or uuid.uuid4().hex
    workspace = FamilyWorkspace(id=workspace_id, name=name, created_by=user_id)
    db.session.add(workspace)
    db.session.flush()
    db.session.add(
        WorkspaceMembership(
            id=uuid.uuid4().hex,
            workspace_id=workspace_id,
            user_id=user_id,
            role="owner",
            status="active",
        )
    )
    # Legacy owner keys retained only for migration/provenance and offline tools.
    if db.session.get(Owner, workspace_id) is None:
        db.session.add(Owner(id=workspace_id, created_at=today_string()))
    audit("workspace.created", workspace_id, user_id, workspace_id)
    return workspace


def scope(model, legacy_owner):
    if has_request_context():
        workspace_id = getattr(g, "workspace_id", None)
        if not workspace_id:
            abort(403)
        return (model.workspace_id == workspace_id) & (
            model.profile_id == getattr(g, "profile_id", None)
        )
    # Explicit offline legacy maintenance/test calls cannot be reached by browsers.
    return model.owner_id == legacy_owner


def association():
    if not has_request_context():
        return {}
    return dict(workspace_id=g.workspace_id, profile_id=g.profile_id)


def care_audit(event_type, target_id=None):
    if has_request_context() and getattr(g, "workspace_id", None):
        audit(
            event_type,
            g.workspace_id,
            current_user.id,
            str(target_id) if target_id is not None else None,
        )
