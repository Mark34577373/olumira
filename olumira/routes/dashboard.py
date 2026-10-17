from flask import Blueprint, g, render_template
from services.dashboard import dashboard_context

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def dashboard():
    return render_template("dashboard.html", **dashboard_context(g.owner_id))


@bp.route("/dashboard/preferences", methods=["GET", "POST"])
def preferences():
    from flask import request, redirect, url_for, flash
    from services import dashboard_preferences as service

    error = None
    status = 200
    if request.method == "POST":
        try:
            service.save(request.form)
        except ValueError as exc:
            error = str(exc)
            status = 409
        else:
            flash("Your dashboard preferences are saved.", "success")
            return redirect(url_for("dashboard.dashboard"))
    return (
        render_template(
            "dashboard_preferences.html",
            pref=service.get(),
            sections=service.SECTIONS,
            error=error,
        ),
        status,
    )


@bp.post("/dashboard/preferred-profile")
def preferred_profile():
    from flask import session, redirect, url_for, abort
    from services.dashboard_preferences import get
    from services.workspaces import require
    from olumira.extensions import db
    from olumira.models import CareProfile

    require("workspace.view")
    pref = get()
    profile = (
        db.session.get(CareProfile, pref.preferred_profile_id)
        if pref.preferred_profile_id
        else None
    )
    if profile and profile.workspace_id != g.workspace_id:
        abort(404)
    session["profile_id"] = profile.id if profile else None
    return redirect(url_for("dashboard.dashboard"))
