from flask import (
    Blueprint,
    request,
    render_template,
    redirect,
    url_for,
    flash,
    g,
    Response,
    session,
)
from flask_login import logout_user, current_user
from sqlalchemy import select
from olumira.extensions import db, limiter
from olumira.models import WorkspaceMembership, User
from services import privacy as service

bp = Blueprint("privacy", __name__)


@bp.route("/settings/privacy", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"], key_func=lambda: current_user.get_id())
def index():
    error = None
    token = None
    if request.method == "POST":
        try:
            action = request.form.get("action")
            if action == "export":
                token = service.request_export(request.form)
            elif action == "transfer":
                service.transfer_ownership(request.form)
                flash("The selected member is now an owner.", "success")
                return redirect(url_for("privacy.index"))
            elif action == "workspace":
                service.close_workspace(request.form)
                session.pop("workspace_id", None)
                session.pop("profile_id", None)
                flash(
                    "Workspace access closed for every member. Shared records and backups remain retained for operator review.",
                    "success",
                )
                return redirect(url_for("workspaces.index"))
            elif action == "account":
                service.close_account(request.form)
                logout_user()
                session.clear()
                flash(
                    "Account deleted and identifying account details anonymized. Shared authored history and backups remain retained.",
                    "success",
                )
                return redirect(url_for("auth.login"))
            else:
                raise ValueError("Choose a supported privacy action.")
        except ValueError as exc:
            error = str(exc)
    members = db.session.execute(
        select(WorkspaceMembership, User.display_name)
        .join(User)
        .where(
            WorkspaceMembership.workspace_id == g.workspace_id,
            WorkspaceMembership.status == "active",
            WorkspaceMembership.user_id != current_user.id,
        )
    ).all()
    return render_template(
        "settings/privacy.html", error=error, download_token=token, members=members
    ), (422 if error else 200)


@bp.post("/settings/privacy/download")
@limiter.limit("20 per hour", key_func=lambda: current_user.get_id())
def download():
    try:
        data, filename = service.download(request.form.get("download_token", ""))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("privacy.index"))
    response = Response(data, mimetype="application/json")
    response.headers["Content-Disposition"] = 'attachment; filename="' + filename + '"'
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response
