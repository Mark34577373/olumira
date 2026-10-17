from flask import Blueprint, render_template, request, redirect, url_for, flash
from services import personal_settings as service

bp = Blueprint("settings", __name__)


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    error = None
    status = 200
    if request.method == "POST":
        try:
            service.save(request.form)
        except ValueError as exc:
            error = str(exc)
            status = 422
        else:
            flash("Your personal settings are saved.", "success")
            return redirect(url_for("settings.settings"))
    return (
        render_template("settings/index.html", pref=service.get(), error=error),
        status,
    )
