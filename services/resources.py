"""Curated general guides and personal bookmarks, without diagnostic inference."""

from urllib.parse import urlsplit
from flask import abort
from flask_login import current_user
from sqlalchemy import select, func, or_
from olumira.extensions import db
from olumira.models import Resource, ResourceBookmark, User
from services.workspaces import require
from services.database import transaction


def external_url(value):
    if not value:
        return None
    if len(value) > 1000 or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError("Use a valid HTTPS source URL.")
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.port not in [None, 443]
        ):
            raise ValueError()
    except ValueError:
        raise ValueError(
            "Use an HTTPS source URL without credentials or a custom port."
        )
    return value


def find(identity):
    require("workspace.view")
    row = db.session.scalar(
        select(Resource).where(Resource.id == identity, Resource.published.is_(True))
    )
    if not row:
        abort(404)
    return row


def listing(values):
    require("workspace.view")
    q = values.get("q", "").strip()
    category = values.get("category", "").strip()
    saved = values.get("saved") == "1"
    try:
        page = int(values.get("page", "1"))
    except ValueError:
        raise ValueError("Choose a valid resource page.")
    if len(q) > 120 or len(category) > 60 or not 1 <= page <= 10000:
        raise ValueError("Shorten the resource search or choose a valid page.")
    query = select(Resource).where(Resource.published.is_(True))
    if q:
        query = query.where(
            or_(
                *[
                    c.icontains(q, autoescape=True)
                    for c in [
                        Resource.title,
                        Resource.summary,
                        Resource.category,
                        Resource.tags,
                    ]
                ]
            )
        )
    if category and category != "All":
        query = query.where(Resource.category == category)
    if saved:
        query = query.join(
            ResourceBookmark, ResourceBookmark.resource_id == Resource.id
        ).where(ResourceBookmark.user_id == current_user.id)
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(
        db.session.scalars(
            query.order_by(Resource.title, Resource.id)
            .offset((page - 1) * 20)
            .limit(20)
        )
    )
    return rows, total, page


def bookmarks(identities):
    return set(
        db.session.scalars(
            select(ResourceBookmark.resource_id).where(
                ResourceBookmark.user_id == current_user.id,
                ResourceBookmark.resource_id.in_(identities),
            )
        )
    )


def bookmark(identity, desired):
    require("workspace.view", lock=True)
    if desired not in ["save", "remove"]:
        abort(404)
    with transaction():
        find(identity)
        # A per-user lock also serializes requests from different family contexts.
        from sqlalchemy import update

        db.session.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(auth_version=User.auth_version, updated_at=User.updated_at)
        )
        row = db.session.get(ResourceBookmark, (current_user.id, identity))
        if desired == "save" and not row:
            db.session.add(
                ResourceBookmark(user_id=current_user.id, resource_id=identity)
            )
        elif desired == "remove" and row:
            db.session.delete(row)


def related(row):
    # Transparent same-category recommendations, never inferred diagnoses.
    return list(
        db.session.scalars(
            select(Resource)
            .where(
                Resource.published.is_(True),
                Resource.id != row.id,
                Resource.category == row.category,
            )
            .order_by(Resource.title, Resource.id)
            .limit(3)
        )
    )


def categories():
    return list(
        db.session.scalars(
            select(Resource.category)
            .where(Resource.published.is_(True))
            .distinct()
            .order_by(Resource.category)
        )
    )
