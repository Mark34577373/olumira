"""DAY 36 — PREMIUM EXPERIENCE PHASE 1: GUIDED ONBOARDING.

Saved setup composes existing services in one transaction; it never claims that
legacy users completed a tour or invents starter completion history.
"""

import uuid
from types import SimpleNamespace
from flask import g, abort
from flask_login import current_user
from sqlalchemy import select, update
from olumira.extensions import db
from olumira.models import (
    OnboardingState as State,
    User,
    CareProfile,
    Routine,
    CommunicationBoard as Board,
    utcnow,
    AuditEvent,
)
from services.workspaces import (
    require,
    scope,
    create_workspace,
    create_profile,
    care_audit,
)
from services.database import transaction
from services import routine_builder, communication

STEPS = (
    "Welcome",
    "Family workspace",
    "Care profile",
    "Daily routines",
    "Communication setup",
    "Care team",
    "Explore Olumira",
    "Ready for your day",
)
TOUR = (
    (
        "dashboard.dashboard",
        "Dashboard",
        "Your selected profile, upcoming plans and quick actions in one place.",
    ),
    (
        "routines.routines",
        "Routines",
        "Build a sequence, add a schedule, and guide one step at a time.",
    ),
    (
        "communication.communication",
        "Communication",
        "Open large picture cards in a distraction-free experience.",
    ),
    (
        "observations.observations",
        "Observations",
        "Record a moment and find it in the searchable timeline.",
    ),
    (
        "calendar.calendar",
        "Calendar",
        "See routine schedules, tasks and your own events together.",
    ),
    (
        "resources.resources",
        "Resources",
        "Browse general organizational guides and save useful ones.",
    ),
    (
        "care.tasks",
        "Care team",
        "Coordinate responsibilities and acknowledge handoffs.",
    ),
)


class SetupConflict(ValueError):
    pass


def get():
    require("workspace.view")
    return db.session.get(
        State, (current_user.id, g.workspace_id), populate_existing=True
    ) or SimpleNamespace(
        step=0,
        version=0,
        profile_id=None,
        routine_id=None,
        board_id=None,
        skipped_steps="",
        started_at=None,
        completed_at=None,
        skipped_at=None,
        legacy_exempt=False,
    )


def _state():
    row = get()
    if row.version == 0:
        row = State(
            user_id=current_user.id,
            workspace_id=g.workspace_id,
            step=0,
            version=0,
            skipped_steps="",
            legacy_exempt=False,
            started_at=utcnow(),
        )
        db.session.add(row)
        db.session.flush()
    return row


def _profile(identity):
    if identity and not db.session.scalar(
        select(CareProfile.id).where(
            CareProfile.id == identity, CareProfile.workspace_id == g.workspace_id
        )
    ):
        abort(404)
    g.profile_id = identity or None
    g.profile = db.session.get(CareProfile, identity) if identity else None


def advance(values, expected_step):
    require("workspace.view", lock=True)
    with transaction():
        db.session.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(auth_version=User.auth_version, updated_at=User.updated_at)
        )
        if values.get("scope_workspace") != g.workspace_id:
            raise SetupConflict(
                "Your workspace changed. Resume setup in the selected family."
            )
        state = _state()
        if expected_step < state.step:
            if expected_step == 1:
                try:
                    transition_version = int(values.get("version", "")) + 1
                except ValueError:
                    raise SetupConflict("Reload to resume the saved setup.")
                previous = db.session.scalar(
                    select(AuditEvent.target_id).where(
                        AuditEvent.workspace_id == g.workspace_id,
                        AuditEvent.actor_id == current_user.id,
                        AuditEvent.event_type
                        == f"onboarding.workspace_{transition_version}",
                    )
                )
                if previous:
                    require("workspace.view", previous)
                    destination = db.session.get(State, (current_user.id, previous))
                    return previous, destination.profile_id if destination else None
            return g.workspace_id, state.profile_id
        if expected_step != state.step or str(state.version) != str(
            values.get("version")
        ):
            raise SetupConflict(
                "Setup changed in another tab. Reload to resume the saved step."
            )
        if state.completed_at or state.skipped_at or state.legacy_exempt:
            raise SetupConflict(
                "This setup is finished or optional for an existing member. Use Revisit setup to start guidance again."
            )
        action = values.get("action", "continue")
        if action not in ["continue", "skip", "leave"]:
            raise ValueError("Choose a setup action.")
        if action == "leave":
            state.skipped_at = utcnow()
            state.version += 1
            return g.workspace_id, state.profile_id
        if action == "skip" and state.step not in [3, 4, 5, 6]:
            raise ValueError("This step must be completed before continuing.")
        if action == "skip":
            state.skipped_steps = ",".join(
                sorted(
                    set(filter(None, state.skipped_steps.split(",")))
                    | {str(state.step)}
                )
            )
        elif state.step == 1:
            chosen = values.get("workspace_id") or g.workspace_id
            if values.get("workspace_action") == "new":
                require("workspace.view")
                chosen = create_workspace(
                    current_user.id, values.get("workspace_name")
                ).id
                db.session.flush()
            else:
                require("workspace.view", chosen)
            if chosen != g.workspace_id:
                state.step = 2
                state.version += 1
                care_audit(f"onboarding.workspace_{state.version}", chosen)
                target = db.session.get(State, (current_user.id, chosen))
                if not target:
                    db.session.add(
                        State(
                            user_id=current_user.id,
                            workspace_id=chosen,
                            step=2,
                            version=1,
                            skipped_steps="",
                            legacy_exempt=False,
                            started_at=utcnow(),
                        )
                    )
                return chosen, target.profile_id if target else None
        elif state.step == 2:
            identity = values.get("selected_profile") or None
            if values.get("profile_action") == "new":
                identity = create_profile(
                    dict(display_name=values.get("profile_name"), avatar="leaf")
                ).id
            _profile(identity)
            state.profile_id = identity
            state.routine_id = None
            state.board_id = None
        elif state.step in [3, 4]:
            _profile(state.profile_id)
            if state.step == 3:
                existing = values.get("routine_id")
                if existing:
                    row = routine_builder.find(int(existing))
                    state.routine_id = row.id
                else:
                    require("routines.create")
                    name = values.get("routine_template", "morning")
                    choice = routine_builder.TEMPLATES.get(name)
                    if not choice:
                        raise ValueError(
                            "Choose a starter routine or an existing sequence."
                        )
                    rid, _ = routine_builder.save(
                        dict(
                            name=choice["name"],
                            description="A starter sequence to adapt together.",
                            category=choice["category"],
                            icon=choice["icon"],
                            color=choice["color"],
                            profile_id=state.profile_id or "",
                            steps=[
                                dict(
                                    id="",
                                    title=title,
                                    description="",
                                    icon=choice["icon"],
                                )
                                for title in choice["titles"]
                            ],
                        )
                    )
                    state.routine_id = rid
            else:
                existing = values.get("board_id")
                if existing:
                    state.board_id = communication.find(existing).id
                else:
                    require("communication.manage")
                    draft = communication.template_draft(
                        values.get("board_template", "needs")
                    )
                    draft["profile_id"] = state.profile_id or ""
                    draft["creation_key"] = uuid.uuid4().hex
                    bid, _ = communication.save(draft)
                    state.board_id = bid
        state.step = min(7, state.step + 1)
        state.version += 1
        if state.step == 7:
            state.completed_at = utcnow()
            care_audit("onboarding.completed")
        return g.workspace_id, state.profile_id


def restart(values):
    require("workspace.view", lock=True)
    with transaction():
        if values.get("scope_workspace") != g.workspace_id:
            raise SetupConflict(
                "Your workspace changed. Reload before revisiting setup."
            )
        row = _state()
        if str(row.version) != str(values.get("version")):
            raise SetupConflict("Setup changed. Reload first.")
        row.step = 0
        row.skipped_steps = ""
        row.started_at = utcnow()
        row.completed_at = None
        row.skipped_at = None
        row.legacy_exempt = False
        row.version += 1


def choices(state):
    original = g.profile_id
    try:
        g.profile_id = state.profile_id
        return dict(
            routines=list(
                db.session.scalars(
                    select(Routine)
                    .where(scope(Routine, g.owner_id), Routine.archived_at.is_(None))
                    .order_by(Routine.name, Routine.id)
                    .limit(100)
                )
            ),
            boards=list(
                db.session.scalars(
                    select(Board)
                    .where(scope(Board, g.owner_id), Board.archived_at.is_(None))
                    .order_by(Board.title, Board.id)
                    .limit(100)
                )
            ),
        )
    finally:
        g.profile_id = original
