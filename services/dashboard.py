from services.database import time_greeting
from services.routines import get_routines, group_by_category, summarize_progress
from services.observations import get_observations


def dashboard_context(owner_id):
    from services import dashboard_preferences

    preferences = dashboard_preferences.get()
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
        .where(scope(Observation, owner_id), Observation.archived_at.is_(None))
    )
    timezone = preferences.timezone
    upcoming_routines = []  # Unified calendar below replaces separate expansion.
    completed_runs, saved_runs = today_summary(timezone)
    from services.care_coordination import dashboard as coordination_dashboard

    result = dict(
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

    from datetime import datetime, timedelta
    from flask import g
    from services import calendar, insights, dashboard_preferences
    from services.routine_scheduling import zone
    from olumira.models import (
        CaregiverTask,
        RoutineSessionStep,
        RoutineSession,
        CommunicationBoard,
    )

    timezone = preferences.timezone
    today = datetime.now(zone(timezone)).date()
    selected = set(preferences.sections.split(","))
    period = insights.period(dict(period="7", timezone=timezone))
    metrics = insights.metric_counts(period)
    day_period = insights.period(
        dict(
            period="custom",
            timezone=timezone,
            **{"from": today.isoformat(), "to": today.isoformat()},
        )
    )
    tasks_today = insights.count(
        CaregiverTask,
        CaregiverTask.status == "completed",
        insights.interval(CaregiverTask.completed_at, day_period),
    )
    rows = (
        calendar.events(today, 14, timezone, assigned_only=True)
        if "upcoming" in selected
        else []
    )
    upcoming = [
        row
        for row in rows
        if row["instant"] >= datetime.now(zone(timezone))
        and row["status"].lower() not in ["completed", "canceled", "archived"]
    ][:5]
    progress_counts = (
        {
            sid: (total, done)
            for sid, total, done in db.session.execute(
                select(
                    RoutineSessionStep.session_id,
                    func.count(),
                    func.count(RoutineSessionStep.completed_at),
                )
                .where(
                    RoutineSessionStep.session_id.in_([run.id for run in saved_runs])
                )
                .group_by(RoutineSessionStep.session_id)
            )
        }
        if saved_runs
        else {}
    )
    board = None
    if "communication" in selected:
        from services.communication_preferences import get as communication_preferences

        preference = communication_preferences()
        if preference.default_board_id:
            board = db.session.scalar(
                select(CommunicationBoard).where(
                    CommunicationBoard.id == preference.default_board_id,
                    scope(CommunicationBoard, owner_id),
                    CommunicationBoard.archived_at.is_(None),
                )
            )
        if not board:
            board = db.session.scalar(
                select(CommunicationBoard)
                .where(
                    scope(CommunicationBoard, owner_id),
                    CommunicationBoard.archived_at.is_(None),
                )
                .order_by(CommunicationBoard.updated_at.desc(), CommunicationBoard.id)
                .limit(1)
            )
    hour = datetime.now(zone(timezone)).hour
    result.update(
        greeting=(
            "Good morning"
            if hour < 12
            else "Good afternoon" if hour < 17 else "Good evening"
        ),
        dashboard_preferences=preferences,
        visible_sections=selected,
        upcoming_events=upcoming,
        dashboard_reminders=(
            calendar.reminders(timezone) if "upcoming" in selected else []
        ),
        dashboard_metrics=metrics,
        tasks_completed_today=tasks_today,
        active_routine_count=metrics["active_routines"],
        run_progress=progress_counts,
        default_board=board,
        routine_timezone=timezone,
        checklist_timezone=current_app.config["APP_TIMEZONE"],
    )
    from services.onboarding import get as setup_state, STEPS

    from services.database import today_string
    result["checklist_date"] = today_string()
    result["setup_state"] = setup_state()
    result["setup_steps"] = STEPS
    return result
