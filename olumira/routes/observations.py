from flask import Blueprint, g, redirect, render_template, request, url_for
from services.database import today_string
from services.observations import add_observation, get_observations

bp = Blueprint("observations", __name__)

@bp.route("/observations", methods=["GET", "POST"])
def observations():
    form_values = {"activity": "", "date": today_string(), "notes": "", "mood": "", "tags": ""}

    error = None
    status = 200
    if request.method == "POST":
        submitted = {
            field: request.form.get(field, "").strip()
            for field in form_values
        }
        saved = add_observation(
            g.owner_id,
            submitted["activity"],
            submitted["date"],
            submitted["notes"],
            submitted["mood"],
            submitted["tags"],
        )
        if saved:
            return redirect(url_for("observations.observations", saved="1"))
        form_values = submitted
        error = "We couldn’t save this observation. Enter an activity (up to 120 characters) and a valid date. Notes can have up to 2,000 characters, mood 20, and tags 120. Your workspace can hold 300 observations."
        status = 422

    return render_template(
        "observations.html",
        form_values=form_values,
        observation_error=error,
        observation_saved=request.args.get("saved") == "1",
        observations=get_observations(g.owner_id),
    ), status




@bp.post('/observations/<int:observation_id>/edit')
def edit_observation_route(observation_id):
    from flask import abort, flash
    from services.observations import edit_observation
    from services.workspaces import require
    require('observations.edit')
    result=edit_observation(g.owner_id,observation_id,request.form)
    if result=='missing': abort(404)
    if result=='invalid':
        flash('Observation not updated. Check the activity, date and field lengths.','error')
    else: flash('Observation updated.','success')
    return redirect(url_for('observations.observations'))
