from flask import (
    has_request_context,
    Blueprint,
    g,
    request,
    render_template,
    redirect,
    url_for,
    session,
    abort,
    flash,
)
from services import onboarding as service
from services.workspaces import require
from olumira.extensions import limiter
from flask_login import current_user

bp = Blueprint("onboarding", __name__)


@bp.route("/setup", methods=["GET", "POST"])
@limiter.limit(
    "60 per hour",
    methods=["POST"],
    key_func=lambda: current_user.get_id() or "anonymous",
)
def setup():
    require("workspace.view")
    state = service.get()
    error = None
    status = 200
    if request.method == "POST":
        try:
            if request.form.get("action") == "restart":
                service.restart(request.form)
                workspace, profile = g.workspace_id, g.profile_id
            else:
                try:
                    step = int(request.form.get("step", ""))
                except ValueError:
                    abort(400)
                workspace, profile = service.advance(request.form, step)
        except ValueError as exc:
            error = str(exc)
            status = 409 if isinstance(exc, service.SetupConflict) else 422
        else:
            session["workspace_id"] = workspace
            session["profile_id"] = profile
            return redirect(
                url_for("dashboard.dashboard")
                if request.form.get("action") == "leave"
                else url_for("onboarding.setup") + "#setup-heading"
            )
    state = service.get()
    return (
        render_template(
            "onboarding/setup.html",
            state=state,
            steps=service.STEPS,
            error=error,
            values=request.form,
            choices=service.choices(state),
            routine_templates=service.routine_builder.TEMPLATES,
            board_templates=service.communication.TEMPLATES,
            tour=service.TOUR,
        ),
        status,
    )


@bp.get("/tour")
def tour():
    require("workspace.view")
    try:
        index = int(request.args.get("step", "0"))
    except ValueError:
        abort(400)
    if not 0 <= index < len(service.TOUR):
        abort(404)
    return render_template("onboarding/tour.html", tour=service.TOUR, index=index)


@bp.app_context_processor
def tour_context():
    if not has_request_context():
        return dict(tour_stop=None)
    index = request.args.get("tour", type=int)
    if (
        index is None
        or not 0 <= index < len(service.TOUR)
        or request.endpoint != service.TOUR[index][0]
    ):
        return dict(tour_stop=None)
    endpoint, title, description = service.TOUR[index]
    return dict(
        tour_stop=dict(
            index=index,
            title=title,
            description=description,
            total=len(service.TOUR),
            close=url_for(endpoint),
            next=(
                url_for(service.TOUR[index + 1][0], tour=index + 1)
                if index + 1 < len(service.TOUR)
                else url_for("onboarding.setup")
            ),
        )
    )
