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
        creators=dict(
            db.session.execute(
                select(User.id, User.display_name).where(
                    User.id.in_([row.created_by for row in rows])
                )
            ).all()
        ),
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


@bp.get("/care-plans")
def plans():
    from services import care_plans as plans_service

    return render_template("care/plans.html", plans=plans_service.listing())


@bp.route("/care-plans/new", methods=["GET", "POST"])
@bp.route("/care-plans/<plan_id>/edit", methods=["GET", "POST"])
def plan_editor(plan_id=None):
    from services import care_plans as plans_service

    require("care.manage")
    plan = plans_service.find(plan_id, "care.manage") if plan_id else None
    values = dict(
        title=plan.title if plan else "",
        description=plan.description if plan else "",
        priorities=plan.priorities if plan else "",
        status=plan.status if plan else "active",
        version=plan.version if plan else "",
        profile_id=g.profile_id or "",
        creation_key=uuid.uuid4().hex,
        goal_title="",
    )
    selected = plans_service.selected(plan) if plan else {}
    error = None
    status = 200
    if request.method == "POST":
        context_check()
        values = {key: request.form.get(key, "") for key in values}
        if request.form.get("plan_action") == "draft":
            values["status"] = "draft"
        selected = {name: request.form.getlist(name) for name in plans_service.LINKS}
        try:
            identity = plans_service.save(values, selected, plan_id)
        except ValueError as exc:
            error = str(exc)
            status = 409 if isinstance(exc, care.CareConflict) else 422
        else:
            flash(
                "Care plan saved. Your connected records stay in their original tools.",
                "success",
            )
            return redirect(url_for("care.plan_detail", plan_id=identity))
    return (
        render_template(
            "care/plan_editor.html",
            plan=plan,
            values=values,
            selected=selected,
            choices=plans_service.choices(),
            error=error,
        ),
        status,
    )


@bp.get("/care-plans/<plan_id>")
def plan_detail(plan_id):
    from services import care_plans as plans_service

    plan = plans_service.find(plan_id)
    return render_template(
        "care/plan.html", plan=plan, data=plans_service.overview(plan)
    )


@bp.route("/care-plans/<plan_id>/goals/new", methods=["GET", "POST"])
@bp.route("/care-plans/<plan_id>/goals/<goal_id>/edit", methods=["GET", "POST"])
def goal_editor(plan_id, goal_id=None):
    from services import care_plans as plans_service
    from olumira.models import CareGoal

    plan = plans_service.find(plan_id, "care.manage")
    goal = (
        db.session.scalar(
            select(CareGoal).where(CareGoal.id == goal_id, CareGoal.plan_id == plan.id)
        )
        if goal_id
        else None
    )
    if goal_id and not goal:
        abort(404)
    fields = ["title", "description", "category", "status", "target_date"]
    values = {field: (getattr(goal, field) or "") if goal else "" for field in fields}
    if not goal:
        values.update(category="Daily support", status="planned")
    values["version"] = plan.version
    error = None
    status = 200
    if request.method == "POST":
        context_check()
        values = {key: request.form.get(key, "") for key in values}
        try:
            plans_service.save_goal(plan.id, values, goal_id)
        except ValueError as exc:
            error = str(exc)
            status = 409 if isinstance(exc, care.CareConflict) else 422
        else:
            flash("Support goal saved.", "success")
            return redirect(url_for("care.plan_detail", plan_id=plan.id))
    return (
        render_template("care/goal_editor.html", plan=plan, values=values, error=error),
        status,
    )


@bp.route("/care/handoffs/studio", methods=["GET", "POST"])
@bp.route("/care/handoffs/drafts/<draft_id>", methods=["GET", "POST"])
def handoff_studio(draft_id=None):
    from datetime import timedelta
    from services import handoff_drafts as studio

    require("care.manage")
    draft = studio.find(draft_id) if draft_id else None
    moment = care.utcnow().astimezone(zone(current_app.config["APP_TIMEZONE"]))
    values = dict(
        summary=draft.summary if draft else "",
        profile_id=g.profile_id or "",
        recipient=draft.recipient_id if draft else "",
        creation_key=uuid.uuid4().hex,
        version=draft.version if draft else "",
        state=draft.status if draft else "draft",
        start=(
            aware(draft.period_start)
            .astimezone(zone(current_app.config["APP_TIMEZONE"]))
            .strftime("%Y-%m-%dT%H:%M")
            if draft
            else (moment - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M")
        ),
        end=(
            aware(draft.period_end)
            .astimezone(zone(current_app.config["APP_TIMEZONE"]))
            .strftime("%Y-%m-%dT%H:%M")
            if draft
            else (moment + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
        ),
    )
    error = None
    status = 200
    categories = ["completed", "unfinished", "tasks", "schedule"]
    observations = []
    if request.method == "POST":
        context_check()
        values = {key: request.form.get(key, "") for key in values}
        categories = request.form.getlist("categories")
        observations = request.form.getlist("observation_ids")
        try:
            if request.form.get("studio_action") == "generate":
                if draft and draft.status == "shared":
                    raise ValueError("Create a new draft to generate another handoff.")
                suggestion = studio.generate(values, observations, categories)
                values["summary"] = suggestion["summary"]
                values["state"] = "draft"
                flash(
                    "Suggestion generated for your review. Nothing was saved or shared.",
                    "info",
                )
            else:
                identity = studio.save(values, draft_id)
                flash(
                    "Private handoff draft saved. Review the final preview before sharing.",
                    "success",
                )
                return redirect(url_for("care.handoff_studio", draft_id=identity))
        except ValueError as exc:
            error = str(exc)
            status = 409 if isinstance(exc, care.CareConflict) else 422
    return (
        render_template(
            "care/handoff_studio.html",
            draft=draft,
            values=values,
            error=error,
            members=care.members(),
            choices=care.reference_choices(),
            categories=categories,
            selected_observations=observations,
            drafts=studio.listing(),
        ),
        status,
    )


@bp.post("/care/handoffs/drafts/<draft_id>/share")
def share_handoff_draft(draft_id):
    from services import handoff_drafts as studio

    context_check()
    if request.form.get("confirm") != "share":
        abort(400)
    try:
        identity = studio.share(draft_id, request.form.get("version"))
    except ValueError as exc:
        return failure(exc)
    flash("Reviewed handoff shared with its authorized recipient.", "success")
    return redirect(url_for("care.handoff_detail", handoff_id=identity))
