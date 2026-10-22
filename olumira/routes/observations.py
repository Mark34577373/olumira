from datetime import datetime
from flask import (
    Blueprint,
    g,
    redirect,
    render_template,
    request,
    url_for,
    abort,
    flash,
    current_app,
)
from olumira.models import User
from olumira.extensions import db
from services import journal
from services.database import today_string
from services.workspaces import require

bp = Blueprint("observations", __name__)
FILTERS = (
    "q",
    "category",
    "tag",
    "author",
    "status",
    "period",
    "from",
    "to",
    "timezone",
    "page",
)


def context():
    # Only bounded, allowlisted filter fields; never accept a redirect URL.
    return {
        k: request.values.get("back_" + k, "")[:120]
        for k in FILTERS
        if request.values.get("back_" + k)
    }


def fields(row=None):
    tz = row.timezone if row and row.timezone else current_app.config["APP_TIMEZONE"]
    local = (
        journal.aware(row.observed_at).astimezone(journal.zone(tz))
        if row and row.observed_at
        else None
    )
    return dict(
        activity=row.activity if row else "",
        date=local.date().isoformat() if local else row.date if row else today_string(),
        time=local.strftime("%H:%M:%S") if local else "",
        timezone=tz,
        notes=row.notes or "" if row else "",
        mood=row.mood or "" if row else "",
        tags=row.tags or "" if row else "",
        category=row.category if row else "General notes",
        session_id=row.session_id or "" if row else "",
        task_id=row.task_id or "" if row else "",
        version=row.version if row else "",
        profile_id=g.profile_id or "",
        scope_workspace=g.workspace_id,
    )


@bp.route("/observations", methods=["GET", "POST"])
def observations():
    values = fields()
    error = None
    status = 200
    if request.method == "POST":
        values = {
            key: request.form.get(key, default) for key, default in values.items()
        }
        try:
            journal.save(values)
        except ValueError as exc:
            error = str(exc)
            status = 422
        else:
            flash("Observation saved. Your moment is safely recorded.", "success")
            return redirect(url_for("observations.observations", saved="1"))
    try:
        filters = {k: request.args.get(k, "") for k in FILTERS}
        filters["status"] = filters["status"] or "active"
        page = int(filters.get("page") or 1)
        rows, total = journal.listing(filters, page)
    except ValueError as exc:
        rows = []
        total = 0
        page = 1
        error = str(exc)
        status = 422
    categories, authors = journal.options()
    return (
        render_template(
            "observations.html",
            form_values=values,
            observation_error=error,
            observations=rows,
            total=total,
            page=page,
            filters=filters,
            categories=categories,
            authors=authors,
            author_names=journal.names(rows),
            choices=journal.references(),
        ),
        status,
    )


@bp.get("/observations/timeline")
def timeline():
    return observations()


@bp.get("/observations/<int:observation_id>")
def detail(observation_id):
    row = journal.find(observation_id)
    return render_template(
        "observations/detail.html",
        observation=row,
        author=db.session.get(User, row.author_id) if row.author_id else None,
        back=context(),
    )


@bp.route("/observations/<int:observation_id>/edit", methods=["GET", "POST"])
def edit_observation_route(observation_id):
    require("observations.edit")
    row = journal.find(observation_id)
    values = fields(row)
    error = None
    status = 200
    if request.method == "POST":
        values = {
            key: request.form.get(key, default) for key, default in values.items()
        }
        # Old clients have no version; reject instead of silently overwriting.
        values["version"] = request.form.get("version", "")
        try:
            journal.save(values, observation_id)
        except ValueError as exc:
            error = str(exc)
            status = 409 if isinstance(exc, journal.Conflict) else 422
        else:
            return redirect(
                url_for(
                    "observations.detail",
                    observation_id=row.id,
                    **{"back_" + k: v for k, v in context().items()}
                )
            )
    return (
        render_template(
            "observations/editor.html",
            observation=row,
            form_values=values,
            error=error,
            back=context(),
            categories=journal.CATEGORIES,
            choices=journal.references(row),
        ),
        status,
    )


@bp.post("/observations/<int:observation_id>/<action>")
def archive(observation_id, action):
    if action not in ["archive", "restore"]:
        abort(404)
    if request.form.get("scope_workspace") != g.workspace_id or request.form.get(
        "profile_id", ""
    ) != (g.profile_id or ""):
        abort(409)
    try:
        journal.archive(
            observation_id, request.form.get("version"), action == "archive"
        )
    except ValueError as exc:
        abort(409, description=str(exc))
    return redirect(
        url_for(
            "observations.detail",
            observation_id=observation_id,
            **{"back_" + k: v for k, v in context().items()}
        )
    )


@bp.app_context_processor
def helpers():
    def journal_link(endpoint, identity=None, **overrides):
        values = {k: request.args.get(k, "") for k in FILTERS if request.args.get(k)}
        if request.endpoint not in [
            "observations.observations",
            "observations.timeline",
        ]:
            values = context()
        values.update(overrides)
        if identity is not None:
            return url_for(
                endpoint,
                observation_id=identity,
                **{"back_" + k: v for k, v in values.items()}
            )
        return url_for(endpoint, **values)

    return dict(journal_stamp=journal.stamp, journal_link=journal_link)


@bp.get("/observations/insights")
def insights():
    from services import insights as service
    from services.care_coordination import timeline as activity

    require("analytics.view")
    values = {
        key: request.args.get(key, "")
        for key in ["period", "from", "to", "timezone", "grouping", "category"]
    }
    values["period"] = values["period"] or "30"
    values["grouping"] = values["grouping"] or "daily"
    values["timezone"] = values["timezone"] or current_app.config["APP_TIMEZONE"]
    error = None
    data = None
    try:
        data = service.calculate(service.period(values), values["category"])
    except ValueError as exc:
        error = str(exc)
    recent, _ = activity(limit=5)
    categories, _ = journal.options()
    return render_template(
        "observations/insights.html",
        values=values,
        data=data,
        error=error,
        categories=categories,
        definitions=service.DEFINITIONS,
        recent=recent,
    ), (422 if error else 200)


@bp.route("/observations/reports", methods=["GET", "POST"])
def reports():
    import io
    from flask import send_file
    from services import reports as service

    require("reports.generate")
    values = dict(
        title="Caregiver summary",
        profile_id=g.profile_id or "",
        scope_workspace=g.workspace_id,
        period="30",
        **{"from": "", "to": ""},
        timezone=current_app.config["APP_TIMEZONE"],
        grouping="daily",
        category="",
        format="pdf"
    )
    selected = ["overview", "routines", "observations", "details", "tasks", "handoffs"]
    report = None
    digest = ""
    error = None
    status = 200
    if request.method == "POST":
        values = {key: request.form.get(key, "") for key in values}
        selected = request.form.getlist("sections")
        try:
            config = service.configure(values, selected)
            report = service.build(config)
            digest = service.fingerprint(report)
            action = request.form.get("action", "preview")
            if action not in ["preview", "download"]:
                raise ValueError("Choose preview or download.")
            if action == "download":
                import hmac

                if not hmac.compare_digest(
                    digest, request.form.get("preview_digest", "")
                ):
                    error = "Records or report options changed since the preview. Review the updated preview below before downloading."
                    status = 409
                else:
                    payload = (
                        service.pdf_bytes(report)
                        if config["format"] == "pdf"
                        else service.csv_bytes(report)
                    )
                    response = send_file(
                        io.BytesIO(payload),
                        mimetype=(
                            "application/pdf"
                            if config["format"] == "pdf"
                            else "text/csv; charset=utf-8"
                        ),
                        as_attachment=True,
                        download_name="olumira-caregiver-report." + config["format"],
                        max_age=0,
                    )
                    response.headers["Cache-Control"] = "private, no-store, max-age=0"
                    response.headers["Pragma"] = "no-cache"
                    return response
        except ValueError as exc:
            error = str(exc)
            status = 422
    categories, _ = journal.options()
    return (
        render_template(
            "observations/reports.html",
            values=values,
            selected=selected,
            sections=service.SECTIONS,
            report=report,
            digest=digest,
            error=error,
            categories=categories,
            definitions=__import__(
                "services.insights", fromlist=["DEFINITIONS"]
            ).DEFINITIONS,
        ),
        status,
    )
