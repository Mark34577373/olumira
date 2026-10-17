from flask import Blueprint, render_template
from olumira.content import RESOURCE_TYPES, RESOURCES

bp = Blueprint("resources", __name__)

@bp.route("/resources")
def resources():
    return render_template(
        "resources.html",
        resource_types=RESOURCE_TYPES,
        resources=RESOURCES,
    )


