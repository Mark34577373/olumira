"""Private workspace, profile and collaboration interfaces."""

from flask import (
    Blueprint,
    abort,
    flash,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy import select
from email_validator import EmailNotValidError
from olumira.extensions import db, limiter
from olumira.models import (
    FamilyWorkspace,
    WorkspaceMembership,
    CareProfile,
    WorkspaceInvitation,
    AuditEvent,
    User,
)
from olumira.forms import LinkForm
from services.database import transaction
from services.workspaces import create_workspace, require, audit
from services.collaboration import (
    issue_invitation,
    accept_invitation,
    revoke_invitation,
    change_member,
)

bp = Blueprint("workspaces", __name__, url_prefix="/workspaces")
AVATARS = {"leaf": "🌿", "sun": "☀️", "flower": "🌼", "star": "⭐"}


def active(permission="workspace.view", lock=False):
    require(permission, lock=lock)
    return g.workspace_id


def fail(message):
    flash(message, "error")
    return redirect(url_for("workspaces.settings"))


@bp.get("")
def index():
    return render_template("workspaces/index.html")


@bp.post("/create")
@limiter.limit(lambda: current_app.config["WORKSPACE_CREATE_LIMIT"])
@limiter.limit("10 per hour", key_func=lambda: current_user.get_id() or "anonymous")
def create():
    try:
        with transaction():
            workspace = create_workspace(current_user.id, request.form.get("name"))
    except ValueError as error:
        return render_template("workspaces/index.html", error=str(error)), 422
    session["workspace_id"] = workspace.id
    session.pop("profile_id", None)
    flash(
        "Your private workspace is ready. Add a care profile or start with shared routines.",
        "success",
    )
    return redirect(url_for("workspaces.settings"))


@bp.post("/select")
def select_workspace():
    workspace_id = request.form.get("workspace_id", "")
    if not workspace_id:
        abort(404)
    require("workspace.view", workspace_id)
    session["workspace_id"] = workspace_id
    session.pop("profile_id", None)
    flash("Workspace switched. Workspace-wide care is active.", "success")
    return redirect(url_for("dashboard.dashboard"))


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    workspace_id = active()
    if request.method == "POST":
        with transaction():
            require("workspace.manage", lock=True)
            name = (request.form.get("name") or "").strip()
            if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
                return fail("Use a workspace name of 1–80 characters.")
            workspace = db.session.get(FamilyWorkspace, workspace_id)
            workspace.name = name
            audit("workspace.updated", workspace_id, current_user.id, workspace_id)
        flash("Workspace updated.", "success")
        return redirect(url_for("workspaces.settings"))
    members = db.session.execute(
        select(WorkspaceMembership, User.display_name)
        .join(User)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.status == "active",
        )
        .order_by(WorkspaceMembership.joined_at)
    ).all()
    invitations = (
        list(
            db.session.scalars(
                select(WorkspaceInvitation)
                .where(WorkspaceInvitation.workspace_id == workspace_id)
                .order_by(WorkspaceInvitation.created_at.desc())
                .limit(100)
            )
        )
        if g.membership.role == "owner"
        else []
    )
    events = (
        list(
            db.session.scalars(
                select(AuditEvent)
                .where(AuditEvent.workspace_id == workspace_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(50)
            )
        )
        if g.membership.role == "owner"
        else []
    )
    import time

    return render_template(
        "workspaces/settings.html",
        members=members,
        invitations=invitations,
        events=events,
        moment=int(time.time()),
    )


def profile_values():
    from services.workspaces import profile_values as validate

    return validate(request.form)


@bp.route("/profiles/new", methods=["GET", "POST"])
def new_profile():
    active("profiles.create")
    if request.method == "POST":
        try:
            from services.workspaces import create_profile

            profile = create_profile(request.form)
            session["profile_id"] = profile.id
            flash("Care profile created.", "success")
            return redirect(
                url_for("workspaces.profile_overview", profile_id=profile.id)
            )
        except ValueError as error:
            return (
                render_template(
                    "workspaces/profile_form.html",
                    profile=None,
                    values=request.form,
                    avatars=AVATARS,
                    error=str(error),
                ),
                422,
            )
    return render_template(
        "workspaces/profile_form.html", profile=None, values={}, avatars=AVATARS
    )


def get_profile(profile_id):
    active("profiles.view")
    profile = db.session.scalar(
        select(CareProfile).where(
            CareProfile.id == profile_id, CareProfile.workspace_id == g.workspace_id
        )
    )
    if not profile:
        abort(404)
    return profile


@bp.post("/profiles/select")
def select_profile():
    active("profiles.view")
    profile_id = request.form.get("profile_id")
    if profile_id:
        get_profile(profile_id)
    session["profile_id"] = profile_id or None
    flash(
        "Care profile switched." if profile_id else "Workspace-wide care is active.",
        "success",
    )
    return redirect(
        url_for(
            {
                "communication": "communication.open_personal_board",
                "observations": "observations.timeline",
                "calendar": "calendar.calendar",
            }.get(request.form.get("return_to"), "dashboard.dashboard")
        )
    )


@bp.get("/profiles/<profile_id>")
def profile_overview(profile_id):
    profile = get_profile(profile_id)
    # Explicit profile overview does not mutate the user's selection.
    g.profile, g.profile_id = profile, profile.id
    from services.dashboard import dashboard_context

    return render_template(
        "workspaces/profile.html",
        profile=profile,
        avatars=AVATARS,
        **dashboard_context(g.workspace_id)
    )


@bp.route("/profiles/<profile_id>/edit", methods=["GET", "POST"])
def edit_profile(profile_id):
    active("profiles.edit")
    profile = get_profile(profile_id)
    if request.method == "POST":
        try:
            values = profile_values()
            with transaction():
                require("profiles.edit", lock=True)
                profile = get_profile(profile_id)
                for key, value in values.items():
                    setattr(profile, key, value)
                audit("profile.updated", g.workspace_id, current_user.id, profile.id)
            flash("Care profile updated.", "success")
            return redirect(
                url_for("workspaces.profile_overview", profile_id=profile.id)
            )
        except ValueError as error:
            return (
                render_template(
                    "workspaces/profile_form.html",
                    profile=profile,
                    values=request.form,
                    avatars=AVATARS,
                    error=str(error),
                ),
                422,
            )
    return render_template(
        "workspaces/profile_form.html", profile=profile, values=profile, avatars=AVATARS
    )


@bp.post("/invite")
@limiter.limit(lambda: current_app.config["WORKSPACE_INVITE_LIMIT"])
@limiter.limit("20 per hour", key_func=lambda: current_user.get_id() or "anonymous")
def invite():
    active("members.invite")
    try:
        issue_invitation(
            g.workspace_id, request.form.get("email"), request.form.get("role")
        )
    except (ValueError, EmailNotValidError) as error:
        return fail(
            "Invitation not sent. Check the email, role, and whether the caregiver is already a member."
        )
    except Exception:
        db.session.rollback()
        current_app.logger.error("Workspace invitation queue failed; details redacted")
        return (
            render_template(
                "error.html",
                code=503,
                heading="Please try again shortly",
                message="The invitation could not be queued. No invitation was issued.",
            ),
            503,
        )
    flash(
        "Invitation queued. In local development, use the private email preview.",
        "success",
    )
    return redirect(url_for("workspaces.settings"))


@bp.post("/invitations/<invitation_id>/revoke")
def revoke(invitation_id):
    active("members.invite")
    if not revoke_invitation(g.workspace_id, invitation_id):
        abort(404)
    flash("Invitation revoked.", "success")
    return redirect(url_for("workspaces.settings"))


@bp.post("/invitations/<invitation_id>/resend")
@limiter.limit(lambda: current_app.config["WORKSPACE_INVITE_LIMIT"])
@limiter.limit("20 per hour", key_func=lambda: current_user.get_id() or "anonymous")
def resend(invitation_id):
    active("members.invite")
    try:
        issue_invitation(g.workspace_id, resend_id=invitation_id)
    except ValueError:
        return fail("A fresh invitation could not be issued.")
    flash("A fresh invitation is queued. The earlier link no longer works.", "success")
    return redirect(url_for("workspaces.settings"))


@bp.route("/accept", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def accept():
    form = LinkForm()
    authorized = current_user.is_authenticated and current_user.email_verified
    if request.method == "POST":
        if not authorized:
            abort(403)
        if form.validate_on_submit():
            workspace_id = accept_invitation(form.recovery_code.data)
            if workspace_id:
                session["workspace_id"] = workspace_id
                session.pop("profile_id", None)
                flash("You’ve joined the workspace.", "success")
                return redirect(url_for("dashboard.dashboard"))
            form.recovery_code.data = ""
            return (
                render_template(
                    "workspaces/accept.html",
                    form=form,
                    authorized=authorized,
                    error="This invitation is unavailable. It may be expired, used, revoked, or addressed to another email. Ask the workspace owner for a fresh invitation.",
                ),
                410,
            )
        return (
            render_template(
                "workspaces/accept.html",
                form=form,
                authorized=authorized,
                error="Paste the complete invitation code.",
            ),
            422,
        )
    return render_template("workspaces/accept.html", form=form, authorized=authorized)


@bp.post("/members/<member_id>/<action>")
def manage_member(member_id, action):
    active("members.manage")
    try:
        change_member(g.workspace_id, member_id, action, request.form.get("role"))
    except ValueError as error:
        return fail(str(error))
    flash(
        "Membership updated. Access changes take effect on the next request.", "success"
    )
    return redirect(url_for("workspaces.settings"))
