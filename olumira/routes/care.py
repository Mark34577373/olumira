"""Care coordination shares the verified workspace/profile boundary."""

import uuid
from flask import (
    Blueprint,
    abort,
    g,
    request,
    render_template,
    redirect,
    url_for,
    session,
    flash,
    current_app,
)
from flask_login import current_user
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import (
    CaregiverTask as Task,
    CaregiverHandoff as Handoff,
    HandoffTask,
    Observation,
    User,
)
from services import care_coordination as care
from services.workspaces import require, scope
from services.routine_scheduling import aware, zone

bp = Blueprint("care", __name__)


def context_check():
    if request.form.get("scope_workspace") != g.workspace_id:
        abort(
            409, description="Your workspace changed. Reopen this form before saving."
        )


def failure(exc):
    return (
        render_template(
            "error.html", code=409, heading="Review this care update", message=str(exc)
        ),
        409,
    )


def page_number():
    try:
        return int(request.args.get("page", "1"))
    except ValueError:
        abort(400)


@bp.get("/care/tasks")
def tasks():
    filters = {key: request.args.get(key, "") for key in ["view", "status", "assignee"]}
    filters["view"] = filters["view"] or "all"
    rows, total = care.task_list(filters, page_number())
    return render_template(
        "care/tasks.html",
        tasks=rows,
        assignee_names=dict(
            db.session.execute(
                select(User.id, User.display_name).where(
                    User.id.in_([t.assigned_to for t in rows if t.assigned_to])
                )
            ).all()
        ),
        total=total,
        page=page_number(),
        filters=filters,
        members=care.members(),
        statuses=care.STATUSES,
        now=care.utcnow(),
    )


@bp.route("/care/tasks/new", methods=["GET", "POST"])
@bp.route("/care/tasks/<task_id>/edit", methods=["GET", "POST"])
def task_editor(task_id=None):
    require("care.manage")
    task = care.find(Task, task_id, "care.manage") if task_id else None
    values = dict(
        title=task.title if task else "",
        description=task.description if task else "",
        profile_id=(task.profile_id if task else g.profile_id) or "",
        assigned_to=task.assigned_to if task else "",
        routine_id=task.routine_id if task else "",
        due_at=(
            aware(task.due_at)
            .astimezone(zone(task.timezone))
            .strftime("%Y-%m-%dT%H:%M")
            if task and task.due_at
            else ""
        ),
        timezone=task.timezone if task else current_app.config["APP_TIMEZONE"],
        priority=task.priority if task else "normal",
        version=task.version if task else "",
        creation_key=uuid.uuid4().hex,
    )
    error = None
    status = 200
    if request.method == "POST":
        context_check()
        values = {key: request.form.get(key, "") for key in values}
        try:
            identity, profile = care.save_task(values, task_id)
        except ValueError as exc:
            error, status = str(exc), 409 if isinstance(exc, care.CareConflict) else 422
        else:
            session["profile_id"] = profile
            flash("Caregiver task saved.", "success")
            return redirect(url_for("care.task_detail", task_id=identity))
    return (
        render_template(
            "care/task_editor.html",
            task=task,
            values=values,
            error=error,
            members=care.members(),
            inactive_assignee=bool(
                values["assigned_to"]
                and not any(
                    m.user_id == values["assigned_to"] for m, _ in care.members()
                )
            ),
            choices=care.reference_choices(),
        ),
        status,
    )


@bp.get("/care/tasks/<task_id>")
def task_detail(task_id):
    task = care.find(Task, task_id)
    assignee = db.session.get(User, task.assigned_to) if task.assigned_to else None
    return render_template(
        "care/task.html",
        task=task,
        assignee=assignee,
        assignee_active=any(m.user_id == task.assigned_to for m, _ in care.members()),
        statuses=care.STATUSES,
        transitions=care.TRANSITIONS[task.status],
    )


@bp.post("/care/tasks/<task_id>/status/<status>")
def task_status(task_id, status):
    context_check()
    try:
        care.change_status(task_id, status, request.form.get("version"))
    except care.InvalidCare as exc:
        return failure(exc)
    return redirect(url_for("care.task_detail", task_id=task_id))


@bp.get("/care/handoffs")
def handoffs():
    filters = {
        key: request.args.get(key, "") for key in ["status", "from", "to", "inbox"]
    }
    filters["status"] = filters["status"] or "all"
    try:
        rows, recipients, total = care.handoff_list(filters, page_number())
    except ValueError as exc:
        abort(400, description=str(exc))
    return render_template(
        "care/handoffs.html",
        handoffs=rows,
        recipients=recipients,
        total=total,
        page=page_number(),
        filters=filters,
        timezone=current_app.config["APP_TIMEZONE"],
    )


@bp.route("/care/handoffs/new", methods=["GET", "POST"])
def handoff_editor():
    require("care.manage")
    values = dict(
        summary="",
        profile_id=g.profile_id or "",
        recipient="team",
        routine_id="",
        observation_id="",
        creation_key=uuid.uuid4().hex,
    )
    selected = []
    error = None
    status = 200
    if request.method == "POST":
        context_check()
        values = {key: request.form.get(key, "") for key in values}
        selected = request.form.getlist("task_ids")
        try:
            identity, profile = care.create_handoff(values, selected)
        except ValueError as exc:
            error, status = str(exc), 422
        else:
            session["profile_id"] = profile
            flash("Handoff shared with its recipients.", "success")
            return redirect(url_for("care.handoff_detail", handoff_id=identity))
    return (
        render_template(
            "care/handoff_editor.html",
            values=values,
            selected=selected,
            error=error,
            members=care.members(),
            choices=care.reference_choices(),
        ),
        status,
    )


@bp.get("/care/handoffs/<handoff_id>")
def handoff_detail(handoff_id):
    handoff = care.find(Handoff, handoff_id)
    tasks = list(
        db.session.scalars(
            select(Task)
            .join(HandoffTask, HandoffTask.task_id == Task.id)
            .where(HandoffTask.handoff_id == handoff.id, scope(Task, g.workspace_id))
        )
    )
    recipients = care.recipients_for([handoff.id])[handoff.id]
    creator = db.session.get(User, handoff.created_by)
    return render_template(
        "care/handoff.html",
        handoff=handoff,
        tasks=tasks,
        recipients=recipients,
        creator=creator,
        can_ack=any(
            r.user_id == current_user.id and not r.acknowledged_at
            for r, _, _, _ in recipients
        ),
    )


@bp.post("/care/handoffs/<handoff_id>/acknowledge")
def acknowledge(handoff_id):
    context_check()
    care.acknowledge(handoff_id)
    flash("Handoff acknowledged.", "success")
    return redirect(url_for("care.handoff_detail", handoff_id=handoff_id))


@bp.get("/care/activity")
def activity():
    rows, has_more = care.timeline(page=page_number())
    return render_template(
        "care/activity.html", events=rows, has_more=has_more, page=page_number()
    )


@bp.get("/care/observations/<int:observation_id>")
def observation_detail(observation_id):
    require("observations.view")
    observation = care.find(Observation, observation_id)
    return render_template("care/observation.html", observation=observation)


@bp.app_context_processor
def care_helpers():
    def activity_url(event, endpoint):
        key = {
            "care.task_detail": "task_id",
            "care.handoff_detail": "handoff_id",
            "routines.routine_player": "session_id",
            "care.observation_detail": "observation_id",
            "communication.board_view": "board_id",
        }[endpoint]
        return url_for(endpoint, **{key: event.target_id})

    return dict(activity_url=activity_url)
