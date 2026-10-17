"""Workspace invitation tokens and membership changes share a workspace lock."""

import hashlib
import json
import re
import secrets
import time
import uuid
from flask import current_app, render_template
from flask_login import current_user
from sqlalchemy import select, update
from olumira.extensions import db
from olumira.models import (
    WorkspaceInvitation,
    WorkspaceMembership,
    FamilyWorkspace,
    EmailOutbox,
    User,
)
from services.authentication import normalize_email
from services.workspaces import require, audit, lock_workspace
from services.database import transaction
from services.email_delivery import cipher


def cancel_mail(invitation_id):
    db.session.execute(
        update(EmailOutbox)
        .where(
            EmailOutbox.invitation_id == invitation_id,
            EmailOutbox.delivered_at.is_(None),
        )
        .values(cancelled_at=int(time.time()))
    )


def issue_invitation(workspace_id, email=None, role=None, *, resend_id=None):
    with transaction():
        require("members.invite", workspace_id, lock=True)
        if resend_id:
            old = db.session.scalar(
                select(WorkspaceInvitation).where(
                    WorkspaceInvitation.id == resend_id,
                    WorkspaceInvitation.workspace_id == workspace_id,
                )
            )
            if not old or old.accepted_at is not None or old.revoked_at is not None:
                from flask import abort

                abort(404)
            email, role = old.email, old.role
        email = normalize_email(email)
        if role not in {"caregiver", "viewer"}:
            raise ValueError("Choose caregiver or viewer.")
        existing = db.session.scalar(
            select(User.id)
            .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.status == "active",
                User.email == email,
            )
        )
        if existing:
            raise ValueError("This caregiver is already a member.")
        moment = int(time.time())
        pending = list(
            db.session.scalars(
                select(WorkspaceInvitation).where(
                    WorkspaceInvitation.workspace_id == workspace_id,
                    WorkspaceInvitation.email == email,
                    WorkspaceInvitation.accepted_at.is_(None),
                    WorkspaceInvitation.revoked_at.is_(None),
                )
            )
        )
        for old in pending:
            old.revoked_at = moment
            cancel_mail(old.id)
        raw = secrets.token_urlsafe(32)
        invitation = WorkspaceInvitation(
            id=uuid.uuid4().hex,
            workspace_id=workspace_id,
            email=email,
            role=role,
            invited_by=current_user.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            created_at=moment,
            expires_at=moment + current_app.config["INVITATION_SECONDS"],
        )
        db.session.add(invitation)
        db.session.flush()
        workspace = db.session.get(FamilyWorkspace, workspace_id)
        link = (
            current_app.config["PUBLIC_APP_URL"].rstrip("/")
            + "/workspaces/accept#token="
            + raw
        )
        values = dict(
            workspace_name=workspace.name,
            link=link,
            code=raw,
            minutes=current_app.config["INVITATION_SECONDS"] // 60,
        )
        payload = dict(
            recipient=email,
            subject="You’re invited to an Olumira workspace",
            text=render_template("emails/invitation.txt", **values),
            html=render_template("emails/invitation.html", **values),
        )
        db.session.add(
            EmailOutbox(
                id=uuid.uuid4().hex,
                user_id=current_user.id,
                invitation_id=invitation.id,
                kind="invitation",
                encrypted_payload=cipher()
                .encrypt(json.dumps(payload).encode())
                .decode(),
                created_at=moment,
                expires_at=invitation.expires_at,
                available_at=moment,
                attempts=0,
            )
        )
        audit("invitation.sent", workspace_id, current_user.id, invitation.id)
    return invitation


def accept_invitation(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", raw):
        return None
    digest = hashlib.sha256(raw.encode()).hexdigest()
    # Read only the workspace key before taking the consistent workspace lock.
    workspace_id = db.session.scalar(
        select(WorkspaceInvitation.workspace_id).where(
            WorkspaceInvitation.token_hash == digest
        )
    )
    if not workspace_id:
        return None
    with transaction():
        lock_workspace(workspace_id)
        user = db.session.scalar(
            select(User)
            .where(User.id == current_user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        invitation = db.session.scalar(
            select(WorkspaceInvitation)
            .where(WorkspaceInvitation.token_hash == digest)
            .execution_options(populate_existing=True)
        )
        moment = int(time.time())
        if (
            not user
            or not user.email_verified
            or not invitation
            or invitation.email != user.email
            or invitation.accepted_at is not None
            or invitation.revoked_at is not None
            or invitation.expires_at <= moment
        ):
            return None
        # Revalidate the inviter: a removed or demoted owner cannot leave live grants.
        inviter = require_inviter(invitation)
        if not inviter:
            return None
        member = db.session.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user.id,
            )
        )
        if member and member.status == "active":
            return None
        claimed = db.session.execute(
            update(WorkspaceInvitation)
            .where(
                WorkspaceInvitation.id == invitation.id,
                WorkspaceInvitation.accepted_at.is_(None),
                WorkspaceInvitation.revoked_at.is_(None),
                WorkspaceInvitation.expires_at > moment,
            )
            .values(accepted_at=moment)
        ).rowcount
        if claimed != 1:
            return None
        if member:
            member.status, member.role = "active", invitation.role
        else:
            db.session.add(
                WorkspaceMembership(
                    id=uuid.uuid4().hex,
                    workspace_id=workspace_id,
                    user_id=user.id,
                    role=invitation.role,
                    status="active",
                )
            )
        cancel_mail(invitation.id)
        audit("member.added", workspace_id, user.id, member.id if member else user.id)
    return workspace_id


def require_inviter(invitation):
    return db.session.scalar(
        select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == invitation.workspace_id,
            WorkspaceMembership.user_id == invitation.invited_by,
            WorkspaceMembership.status == "active",
            WorkspaceMembership.role == "owner",
        )
    )


def revoke_invitation(workspace_id, invitation_id):
    with transaction():
        require("members.invite", workspace_id, lock=True)
        invitation = db.session.scalar(
            select(WorkspaceInvitation).where(
                WorkspaceInvitation.id == invitation_id,
                WorkspaceInvitation.workspace_id == workspace_id,
            )
        )
        if not invitation:
            return False
        if invitation.accepted_at is not None:
            return False
        invitation.revoked_at = int(time.time())
        cancel_mail(invitation.id)
        audit("invitation.revoked", workspace_id, current_user.id, invitation.id)
    return True


def change_member(workspace_id, member_id, action, role=None):
    with transaction():
        require("members.manage", workspace_id, lock=True)
        member = db.session.scalar(
            select(WorkspaceMembership)
            .where(
                WorkspaceMembership.id == member_id,
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.status == "active",
            )
            .execution_options(populate_existing=True)
        )
        if not member:
            raise ValueError("This membership is no longer active.")
        # Explicit policy: no ownership transfer or owner demotion/removal in this release.
        if member.role == "owner":
            raise ValueError(
                "Owners cannot be removed or demoted. Ownership transfer requires a separately reviewed procedure."
            )
        if action == "role" and role not in {"caregiver", "viewer"}:
            raise ValueError("Choose caregiver or viewer.")
        if action == "remove":
            member.status = "revoked"
        elif action == "role":
            member.role = role
        else:
            raise ValueError("Choose an available action.")
        audit(
            "member.removed" if action == "remove" else "member.role_changed",
            workspace_id,
            current_user.id,
            member.id,
        )
