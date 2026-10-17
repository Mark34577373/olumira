from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from services.routines import (ROUTINE_TEMPLATES, add_routine, add_template, delete_routine, get_routines, group_by_category, summarize_progress, toggle_routine, update_routine)

bp = Blueprint("routines", __name__)

@bp.route("/routines/<int:routine_id>/toggle", methods=["POST"])
def toggle_routine_completion(routine_id):
    if not toggle_routine(g.owner_id, routine_id):
        abort(404)
    endpoint = {
        "dashboard": "dashboard.dashboard",
        "routines": "routines.routines",
    }.get(request.form.get("return_to"), "dashboard.dashboard")
    return redirect(url_for(endpoint))


@bp.route("/routines")
def routines():
    routine_list = get_routines(g.owner_id)
    groups = group_by_category(routine_list)
    completed_routines, routine_count, progress = summarize_progress(routine_list)

    return render_template(
        "routines.html",
        routine_groups=groups,
        category_options=sorted(set(groups) | set(ROUTINE_TEMPLATES)),
        template_names=list(ROUTINE_TEMPLATES),
        completed_routines=completed_routines,
        routine_count=routine_count,
        progress=progress,
        error=request.args.get("error"),
    )


@bp.route("/routines/add", methods=["POST"])
def add_routine_route():
    status = add_routine(
        g.owner_id, request.form.get("name"), request.form.get("category")
    )
    return redirect(url_for("routines.routines", error=None if status == "ok" else status))


@bp.route("/routines/<int:routine_id>/edit", methods=["POST"])
def edit_routine_route(routine_id):
    status = update_routine(
        g.owner_id, routine_id, request.form.get("name"), request.form.get("category")
    )
    if status == "missing":
        abort(404)
    return redirect(url_for("routines.routines", error=None if status == "ok" else status))


@bp.route("/routines/<int:routine_id>/delete", methods=["POST"])
def delete_routine_route(routine_id):
    if not delete_routine(g.owner_id, routine_id):
        abort(404)
    return redirect(url_for("routines.routines"))


@bp.route("/routines/add-template", methods=["POST"])
def add_template_route():
    status = add_template(g.owner_id, request.form.get("template"))
    if status == "invalid":
        abort(400)
    return redirect(url_for("routines.routines", error=None if status == "ok" else status))


