from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from services.routines import (
    ROUTINE_TEMPLATES,
    add_routine,
    add_template,
    delete_routine,
    get_routines,
    group_by_category,
    summarize_progress,
    toggle_routine,
    update_routine,
)

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
    from services import routine_builder as builder

    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        abort(400)
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    state = request.args.get("status", "active")
    cards, card_steps, total = builder.library(query, category, state, page)
    routine_list = get_routines(g.owner_id, checklist_only=True)
    groups = group_by_category(routine_list)
    completed_routines, routine_count, progress = summarize_progress(routine_list)

    return render_template(
        "routines.html",
        routine_groups=groups,
        cards=cards,
        card_steps=card_steps,
        library_total=total,
        page=page,
        search=query,
        category_filter=category,
        status_filter=state,
        icons=builder.ICONS,
        colors=builder.COLORS,
        categories=builder.CATEGORIES,
        starter_templates=builder.TEMPLATES,
        category_options=builder.categories_for_scope(),
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
    return redirect(
        url_for("routines.routines", error=None if status == "ok" else status)
    )


@bp.route("/routines/<int:routine_id>/edit", methods=["POST"])
def edit_routine_route(routine_id):
    status = update_routine(
        g.owner_id,
        routine_id,
        request.form.get("name"),
        request.form.get("category"),
        request.form.get("version"),
    )
    if status == "missing":
        abort(404)
    if status == "conflict":
        abort(409)
    return redirect(
        url_for("routines.routines", error=None if status == "ok" else status)
    )


@bp.route("/routines/<int:routine_id>/delete", methods=["POST"])
def delete_routine_route(routine_id):
    status = delete_routine(g.owner_id, routine_id, request.form.get("version"))
    if status == "conflict":
        abort(409)
    if not status:
        abort(404)
    return redirect(url_for("routines.routines"))


@bp.route("/routines/add-template", methods=["POST"])
def add_template_route():
    status = add_template(g.owner_id, request.form.get("template"))
    if status == "invalid":
        abort(400)
    return redirect(
        url_for("routines.routines", error=None if status == "ok" else status)
    )


# Premium builder routes share the same blueprint and authorization boundary.
from flask import flash, session
from services import routine_builder as builder


def _draft_action(values):
    action = request.form.get("builder_action", "")
    if not action:
        return False
    steps = values["steps"]
    if action == "add":
        if len(steps) >= 30:
            raise builder.InvalidRoutine("A routine can have up to 30 steps.")
        steps.append(dict(id="", title="", description="", icon="sun"))
    else:
        try:
            direction, index = action.split(":")
            index = int(index)
        except (ValueError, TypeError):
            abort(400)
        if direction not in {"up", "down", "remove"} or not 0 <= index < len(steps):
            abort(400)
        if direction == "remove":
            if len(steps) <= 1:
                raise builder.InvalidRoutine("Keep at least one step in your routine.")
            steps.pop(index)
        else:
            target = index + (-1 if direction == "up" else 1)
            if 0 <= target < len(steps):
                steps[index], steps[target] = steps[target], steps[index]
    return True


def _builder(values, routine=None, error=None, status=200):
    return (
        render_template(
            "routines/builder.html",
            values=values,
            routine=routine,
            error=error,
            icons=builder.ICONS,
            colors=builder.COLORS,
            categories=builder.CATEGORIES,
            starter_templates=builder.TEMPLATES,
        ),
        status,
    )


@bp.route("/routines/new", methods=["GET", "POST"])
def new_routine():
    from services.workspaces import require

    require("routines.create")
    values = dict(
        name="",
        description="",
        category="Morning",
        icon="sun",
        color="sage",
        profile_id=g.profile_id or "",
        version="",
        steps=[dict(id="", title="", description="", icon="sun")],
    )
    template = request.args.get("template")
    if template:
        choice = builder.TEMPLATES.get(template)
        if not choice:
            abort(404)
        values.update({key: value for key, value in choice.items() if key != "titles"})
        values["steps"] = [
            dict(id="", title=title, description="", icon=choice["icon"])
            for title in choice["titles"]
        ]
    if request.method == "POST":
        try:
            values = builder.from_form(request.form)
            if _draft_action(values):
                return _builder(values)
            routine_id, profile_id = builder.save(values)
        except builder.InvalidRoutine as error:
            # Preserve all structurally valid submitted fields; malformed arrays
            # receive a safe empty draft, never a partially applied write.
            return _builder(values, error=str(error), status=422)
        session["profile_id"] = profile_id
        flash("Your routine is ready. Review the sequence below.", "success")
        return redirect(url_for("routines.routine_sequence", routine_id=routine_id))
    return _builder(values)


@bp.route("/routines/<int:routine_id>/builder", methods=["GET", "POST"])
def edit_builder(routine_id):
    routine = builder.find(routine_id, "routines.edit")
    if routine.archived_at:
        abort(409, description="Restore the routine before editing it.")
    values = builder.draft(routine)
    if request.method == "POST":
        try:
            values = builder.from_form(request.form)
            if _draft_action(values):
                return _builder(values, routine)
            _, profile_id = builder.save(values, routine_id)
        except builder.RoutineConflict as error:
            return _builder(values, routine, error=str(error), status=409)
        except builder.InvalidRoutine as error:
            return _builder(values, routine, error=str(error), status=422)
        session["profile_id"] = profile_id
        flash("Routine saved.", "success")
        return redirect(url_for("routines.routine_sequence", routine_id=routine_id))
    return _builder(values, routine)


@bp.get("/routines/<int:routine_id>")
def routine_sequence(routine_id):
    routine = builder.find(routine_id)
    return render_template(
        "routines/sequence.html",
        routine=routine,
        steps=builder.steps_for(routine.id),
        icons=builder.ICONS,
        launch_key=uuid.uuid4().hex,
    )


@bp.post("/routines/<int:routine_id>/duplicate")
def duplicate_routine(routine_id):
    try:
        copied_id, profile_id = builder.duplicate(
            routine_id, request.form.get("profile_id", "")
        )
    except builder.InvalidRoutine as error:
        flash(str(error), "error")
        return redirect(url_for("routines.routines"))
    session["profile_id"] = profile_id
    flash("Routine duplicated with fresh steps and no completion history.", "success")
    return redirect(url_for("routines.edit_builder", routine_id=copied_id))


@bp.post("/routines/<int:routine_id>/archive")
@bp.post("/routines/<int:routine_id>/restore", endpoint="restore_routine")
def archive_routine(routine_id):
    restore = request.path.endswith("/restore")
    try:
        builder.change_archive(routine_id, request.form.get("version"), restore)
    except builder.RoutineConflict as error:
        return (
            render_template(
                "error.html",
                code=409,
                heading="This routine has changed",
                message=str(error),
            ),
            409,
        )
    except builder.InvalidRoutine as error:
        flash(str(error), "error")
        return redirect(url_for("routines.routines"))
    flash(
        (
            "Routine restored."
            if restore
            else "Routine archived. Its completion history is preserved."
        ),
        "success",
    )
    return redirect(
        url_for("routines.routines", status="archived" if restore else "active")
    )


# Scheduling and guided runs retain the routines authorization and navigation context.
import uuid
from datetime import timedelta
from flask import current_app, jsonify
from services import routine_scheduling as scheduling, routine_sessions as runs


def _zone():
    return request.args.get("timezone", current_app.config["APP_TIMEZONE"])


@bp.get("/routines/calendar")
def routine_calendar():
    tzname = _zone()
    try:
        tz = scheduling.zone(tzname)
        day = (
            scheduling.parse_date(request.args["date"])
            if request.args.get("date")
            else scheduling.utcnow().astimezone(tz).date()
        )
        mode = request.args.get("view", "week")
        if mode not in {"day", "week"} or day.year >= 9998 or day.year <= 1900:
            abort(400)
        days = 1 if mode == "day" else 7
        entries = scheduling.calendar(day, days, tzname)
    except scheduling.InvalidSchedule as error:
        abort(400, description=str(error))
    return render_template(
        "routines/calendar.html",
        entries=entries,
        days=[day + timedelta(days=i) for i in range(days)],
        day=day,
        mode=mode,
        timezone=tzname,
        previous=(day - timedelta(days=days)).isoformat(),
        following=(day + timedelta(days=days)).isoformat(),
        schedules=scheduling.schedule_list(),
        launch_key=uuid.uuid4().hex,
    )


@bp.route("/routines/<int:routine_id>/schedule", methods=["GET", "POST"])
@bp.route("/routines/<int:routine_id>/schedule/<schedule_id>", methods=["GET", "POST"])
def routine_schedule(routine_id, schedule_id=None):
    routine = builder.find(routine_id, "routines.edit")
    schedule = scheduling.find(schedule_id, "routines.edit") if schedule_id else None
    if schedule and schedule.routine_id != routine.id:
        abort(404)
    values = dict(
        timezone=current_app.config["APP_TIMEZONE"],
        local_time="07:00",
        frequency="daily",
        weekdays=[],
        start_date=scheduling.utcnow()
        .astimezone(scheduling.zone(current_app.config["APP_TIMEZONE"]))
        .date()
        .isoformat(),
        end_date="",
        version="",
    )
    if schedule:
        values.update(scheduling.revision_values(scheduling.current_revision(schedule)))
        values["weekdays"] = values["weekdays"].split(",") if values["weekdays"] else []
        values["version"] = schedule.version
    error = None
    status = 200
    if request.method == "POST":
        values = scheduling.values_from_form(request.form)
        try:
            scheduling.save(routine_id, values, schedule_id)
        except scheduling.InvalidSchedule as exc:
            error, status = str(exc), (
                409 if isinstance(exc, scheduling.ScheduleConflict) else 422
            )
        else:
            flash("Schedule saved. Changes apply to future occurrences.", "success")
            return redirect(
                url_for("routines.routine_calendar", timezone=values["timezone"])
            )
    return (
        render_template(
            "routines/schedule.html",
            routine=routine,
            schedule=schedule,
            values=values,
            error=error,
        ),
        status,
    )


@bp.post("/routines/schedules/<schedule_id>/<action>")
def schedule_action(schedule_id, action):
    try:
        scheduling.change_state(schedule_id, action, request.form.get("version"))
    except scheduling.InvalidSchedule as error:
        return (
            render_template(
                "error.html",
                code=409,
                heading="Review this schedule",
                message=str(error),
            ),
            409,
        )
    flash("Schedule updated. Saved runs are preserved.", "success")
    return redirect(url_for("routines.routine_calendar"))


@bp.post("/routines/<int:routine_id>/start")
def start_session(routine_id):
    try:
        run_id = runs.start(
            routine_id,
            request.form.get("launch_key"),
            request.form.get("revision_id") or None,
            request.form.get("local_date"),
        )
    except (runs.RunConflict, scheduling.InvalidSchedule) as error:
        return (
            render_template(
                "error.html",
                code=409,
                heading="Review this routine",
                message=str(error),
            ),
            409,
        )
    return redirect(url_for("routines.routine_player", session_id=run_id))


def _player(session_id, error=None, status=200):
    run = runs.find(session_id)
    steps = runs.steps_for(run.id)
    done = sum(bool(step.completed_at) for step in steps)
    try:
        index = int(
            request.values.get(
                "step",
                next(
                    (i for i, s in enumerate(steps) if not s.completed_at),
                    len(steps) - 1,
                ),
            )
        )
    except (ValueError, TypeError):
        abort(400)
    index = max(0, min(index, len(steps) - 1))
    mode = request.values.get("mode", "guided")
    if mode not in {"guided", "overview"}:
        abort(400)
    return (
        render_template(
            "routines/player.html",
            run=run,
            steps=steps,
            current=steps[index],
            index=index,
            mode=mode,
            done=done,
            percent=round(done * 100 / len(steps)),
            error=error,
            events=runs.activity(run.id),
            action_key=uuid.uuid4().hex,
        ),
        status,
    )


@bp.get("/routines/sessions/<session_id>")
def routine_player(session_id):
    return _player(session_id)


@bp.post("/routines/sessions/<session_id>/action")
def session_action(session_id):
    try:
        runs.mutate(
            session_id,
            request.form.get("action"),
            request.form.get("version"),
            request.form.get("action_id"),
            request.form.get("step_id") or None,
        )
    except runs.RunConflict as error:
        return _player(session_id, str(error), 409)
    # Complete advances to the first unfinished step; other actions keep orientation.
    return redirect(
        url_for(
            "routines.routine_player",
            session_id=session_id,
            mode=request.form.get("mode", "guided"),
            step=(
                None
                if request.form.get("action") == "complete"
                else request.form.get("step")
            ),
        )
    )


@bp.get("/routines/history")
def routine_history():
    try:
        page = int(request.args.get("page", "1"))
        filters = {
            k: request.args.get(k, "") for k in ["status", "routine", "from", "to"]
        }
        filters["timezone"] = _zone()
        rows, counts, total = runs.history(filters, page)
    except (scheduling.InvalidSchedule, ValueError) as error:
        abort(400, description=str(error))
    return render_template(
        "routines/history.html",
        rows=rows,
        counts=counts,
        total=total,
        page=page,
        filters=filters,
    )


@bp.app_context_processor
def routine_helpers():
    def format_time(value, tzname=None):
        if value is None:
            return ""
        return (
            scheduling.aware(value)
            .astimezone(scheduling.zone(tzname or current_app.config["APP_TIMEZONE"]))
            .strftime("%b %d, %Y · %H:%M %Z")
        )

    from sqlalchemy import select
    from olumira.models import RoutineSession
    from olumira.extensions import db
    from services.workspaces import scope

    # Callable options: only history invokes this bounded, snapshot-scoped query.
    def history_routines():
        return db.session.execute(
            select(RoutineSession.routine_id, RoutineSession.title)
            .where(scope(RoutineSession, g.workspace_id))
            .distinct()
            .order_by(RoutineSession.title)
            .limit(200)
        ).all()

    return dict(
        new_key=uuid.uuid4,
        format_time=format_time,
        history_routine_options=history_routines,
    )


@bp.get("/routines/sessions/<session_id>/state")
def session_state(session_id):
    run = runs.find(session_id)
    return jsonify(version=run.version, status=run.status)
