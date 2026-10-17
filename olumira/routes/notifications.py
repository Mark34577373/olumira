from flask import Blueprint, request, render_template, redirect, url_for, flash, abort
from services import notifications as service

bp = Blueprint("notifications", __name__)


@bp.get("/notifications")
def index():
    try:
        page = int(request.args.get("page", "1"))
        rows = service.inbox(
            request.args.get("category", ""), request.args.get("state", "all"), page
        )
    except ValueError:
        abort(400)
    return render_template(
        "notifications/index.html",
        rows=rows[:20],
        more=len(rows) > 20,
        page=page,
        categories=service.CATEGORIES,
    )


@bp.post("/notifications/<identity>/<desired>")
def action(identity, desired):
    destination = service.action(identity, desired)
    flash("Notifications updated.", "success")
    return redirect(destination or url_for("notifications.index"))


@bp.route("/settings/notifications", methods=["GET", "POST"])
def preferences():
    error = None
    if request.method == "POST":
        try:
            service.save_preferences(request.form)
        except ValueError as exc:
            error = str(exc)
        else:
            flash("Notification preferences saved.", "success")
            return redirect(url_for("notifications.preferences"))
    return render_template(
        "notifications/preferences.html",
        pref=service.preferences(),
        categories=service.CATEGORIES,
        error=error,
    ), (422 if error else 200)
