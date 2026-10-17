from flask import Blueprint, g, render_template
from services.dashboard import dashboard_context

bp = Blueprint("dashboard", __name__)

@bp.route("/")
def dashboard():
    return render_template("dashboard.html", **dashboard_context(g.owner_id))
