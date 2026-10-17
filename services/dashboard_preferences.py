"""Personal dashboard choices belong to the member, never the shared care profile."""

from types import SimpleNamespace
from flask import g, abort, current_app
from flask_login import current_user
from sqlalchemy import select
from olumira.extensions import db
from olumira.models import DashboardPreference as Preference, CareProfile
from services.workspaces import require
from services.database import transaction
from services.routine_scheduling import zone

SECTIONS = {
    "upcoming": "Upcoming schedule",
    "runs": "Guided routine progress",
    "communication": "Communication shortcuts",
    "observations": "Recent observations",
    "collaboration": "Care-team collaboration",
    "insights": "Last 7 days insights",
}


def get():
    require("workspace.view")
    return db.session.get(
        Preference, (current_user.id, g.workspace_id)
    ) or SimpleNamespace(
        preferred_profile_id=None,
        sections=",".join(SECTIONS),
        timezone=current_app.config["APP_TIMEZONE"],
        version=0,
    )


def save(values):
    require("workspace.view", lock=True)
    with transaction():
        if values.get("scope_workspace") != g.workspace_id:
            raise ValueError("Your workspace changed. Reload these preferences.")
        pref = get()
        if str(pref.version) != str(values.get("version")):
            raise ValueError("Preferences changed. Reload before saving.")
        identity = values.get("preferred_profile_id") or None
        if identity and not db.session.scalar(
            select(CareProfile.id).where(
                CareProfile.id == identity, CareProfile.workspace_id == g.workspace_id
            )
        ):
            abort(404)
        sections = (
            values.getlist("sections")
            if hasattr(values, "getlist")
            else values.get("sections", [])
        )
        if any(s not in SECTIONS for s in sections):
            raise ValueError("Choose valid dashboard sections.")
        tz = str(zone(values.get("timezone", "")))
        if pref.version == 0:
            pref = Preference(
                user_id=current_user.id, workspace_id=g.workspace_id, version=0
            )
            db.session.add(pref)
        pref.preferred_profile_id = identity
        pref.timezone = tz
        pref.sections = ",".join(s for s in SECTIONS if s in sections)
        pref.version += 1
