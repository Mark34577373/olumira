from flask import Blueprint, render_template, request, redirect, url_for, abort
from services import resources as service

bp = Blueprint("resources", __name__)


@bp.get("/resources")
def resources():
    values = {k: request.args.get(k, "") for k in ["q", "category", "saved", "page"]}
    values["page"] = values["page"] or "1"
    try:
        rows, total, page = service.listing(values)
    except ValueError as exc:
        abort(400, description=str(exc))
    data = [
        dict(
            id=r.id,
            title=r.title,
            category=r.category,
            summary=r.summary,
            details=r.content,
            publisher=r.publisher,
            action="Quick read",
        )
        for r in rows
    ]
    return render_template(
        "resources.html",
        resources=data,
        resource_types=["All"] + service.categories(),
        values=values,
        total=total,
        page=page,
        bookmarks=service.bookmarks([r.id for r in rows]),
    )


@bp.get("/resources/<identity>")
def detail(identity):
    row = service.find(identity)
    try:
        external = service.external_url(row.external_url)
    except ValueError:
        external = None
    return render_template(
        "resources/detail.html",
        resource=row,
        external=external,
        saved=row.id in service.bookmarks([row.id]),
        related=service.related(row),
    )


@bp.post("/resources/<identity>/bookmark/<desired>")
def bookmark(identity, desired):
    service.bookmark(identity, desired)
    return redirect(
        url_for("resources.resources", saved="1")
        if request.form.get("return_to") == "saved"
        else url_for("resources.detail", identity=identity)
    )
