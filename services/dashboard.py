from services.database import time_greeting
from services.routines import get_routines, group_by_category, summarize_progress
from services.observations import get_observations


def dashboard_context(owner_id):
    routines = get_routines(owner_id, checklist_only=True)
    completed, total, progress = summarize_progress(routines)
    groups = group_by_category(routines)
    from services.routine_builder import dashboard_sequences

    sequences, sequence_count = dashboard_sequences(owner_id)
    observations = get_observations(owner_id, limit=2)
    from sqlalchemy import select, func
    from flask import current_app
    from olumira.extensions import db
    from olumira.models import Observation
    from services.workspaces import scope
    from services.routine_scheduling import upcoming
    from services.routine_sessions import today_summary

    observation_count = db.session.scalar(
        select(func.count())
        .select_from(Observation)
        .where(scope(Observation, owner_id))
    )
    timezone = current_app.config["APP_TIMEZONE"]
    upcoming_routines = upcoming(timezone)
    completed_runs, saved_runs = today_summary(timezone)
    from services.care_coordination import dashboard as coordination_dashboard
    return dict(
        **coordination_dashboard(),
        greeting=time_greeting(),
        routine_groups=groups,
        completed_routines=completed,
        routine_count=total,
        progress=progress,
        recent_observations=observations[:2],
        observation_count=observation_count,
        active_routine_count=len(groups),
        routine_sequences=sequences,
        routine_sequence_count=sequence_count,
        upcoming_routines=upcoming_routines,
        completed_runs=completed_runs,
        saved_runs=saved_runs,
        routine_timezone=timezone,
    )
