from flask import Blueprint, render_template
from olumira.content import COMMUNICATION_OPTIONS

bp = Blueprint("communication", __name__)

@bp.route("/communication")
def communication():
    return render_template(
        "communication.html",
        communication_categories=("Needs", "Activities"),
        communication_options=COMMUNICATION_OPTIONS,
    )


