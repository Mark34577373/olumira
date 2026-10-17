import uuid
from flask import (
    Blueprint,
    g,
    request,
    render_template,
    redirect,
    url_for,
    abort,
    session,
    current_app,
    flash,
)
from services import calendar as service
from services.workspaces import require

bp = Blueprint("calendar", __name__)


def fields(row=None):
    day = (
        service.datetime.now(
            service.scheduling.zone(current_app.config["APP_TIMEZONE"])
        )
        .date()
        .isoformat()
    )
    return dict(
        title=row.title if row else "",
        description=row.description if row else "",
        start_date=row.start_date if row else day,
        local_time=row.local_time if row else "09:00",
        end_date=row.end_date if row else day,
        end_time=row.end_time if row else "10:00",
        timezone=row.timezone if row else current_app.config["APP_TIMEZONE"],
        frequency=row.frequency if row else "once",
        repeat_until=row.repeat_until or "" if row else "",
        assigned_to=row.assigned_to or "" if row else "",
        all_day="on" if row and row.all_day else "",
        weekdays=row.weekdays.split(",") if row and row.weekdays else [],
        version=row.version if row else "",
        creation_key=uuid.uuid4().hex,
        scope_workspace=g.workspace_id,
        profile_id=g.profile_id or "",
    )


@bp.get("/calendar")
def calendar():
    values = request.args.to_dict()
    values.setdefault("view", session.get("calendar_view", "month"))
    try:
        period = service.window(values)
        rows = service.events(
            period["start"],
            period["days"],
            period["timezone"],
            values.get("type", ""),
            values.get("status") == "all",
        )
        reminders = service.reminders(period["timezone"])
    except ValueError as exc:
        return (
            render_template(
                "error.html",
                code=422,
                heading="Review calendar options",
                message=str(exc),
            ),
            422,
        )
    session["calendar_view"] = period["view"]
    days = []
    for n in range(period["days"]):
        day = period["start"] + service.timedelta(days=n)
        lower = service.datetime.combine(
            day, service.time.min, service.scheduling.zone(period["timezone"])
        )
        upper = lower + service.timedelta(days=1)
        days.append(
            (
                day,
                [
                    r
                    for r in rows
                    if r["instant"] < upper
                    and (r["end"] > lower or r["instant"] >= lower)
                ],
            )
        )
    return render_template(
        "calendar/index.html",
        period=period,
        rows=rows,
        days=days,
        types=service.TYPES,
        kind=values.get("type", ""),
        visibility=values.get("status", "active"),
        reminders=reminders,
    )


@bp.route("/calendar/new", methods=["GET", "POST"])
@bp.route("/calendar/<identity>/edit", methods=["GET", "POST"])
def editor(identity=None):
    require("calendar.manage")
    row = service.find(identity) if identity else None
    values = fields(row)
    error = None
    status = 200
    if request.method == "POST":
        values = request.form.to_dict()
        values["weekdays"] = request.form.getlist("weekdays")
        try:
            result = service.save(request.form, identity)
        except ValueError as exc:
            error = str(exc)
            status = 409 if isinstance(exc, service.CalendarConflict) else 422
        else:
            return redirect(url_for("calendar.detail", identity=result))
    return (
        render_template(
            "calendar/editor.html",
            event=row,
            values=values,
            error=error,
            members=service.members(),
        ),
        status,
    )


@bp.get("/calendar/<identity>")
def detail(identity):
    row = service.find(identity)
    return render_template(
        "calendar/detail.html", event=row, members=dict(service.members())
    )


@bp.post("/calendar/<identity>/status/<desired>")
def status(identity, desired):
    if request.form.get("confirm") != "yes":
        abort(400)
    try:
        service.status(identity, request.form, desired)
    except ValueError as exc:
        abort(409, description=str(exc))
    return redirect(url_for("calendar.detail", identity=identity))


@bp.route("/calendar/reminders", methods=["GET", "POST"])
def preferences():
    error = None
    status = 200
    if request.method == "POST":
        try:
            service.save_preferences(request.form)
        except ValueError as exc:
            error = str(exc)
            status = 409 if isinstance(exc, service.CalendarConflict) else 422
        else:
            flash("In-app reminder preferences saved.", "success")
            return redirect(url_for("calendar.preferences"))
    return (
        render_template(
            "calendar/reminders.html", pref=service.preferences(), error=error
        ),
        status,
    )
