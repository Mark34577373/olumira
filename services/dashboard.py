from services.database import time_greeting
from services.routines import get_routines, group_by_category, summarize_progress
from services.observations import get_observations


def dashboard_context(owner_id):
    routines = get_routines(owner_id)
    completed, total, progress = summarize_progress(routines)
    groups = group_by_category(routines)
    observations = get_observations(owner_id)
    return dict(greeting=time_greeting(), routine_groups=groups,
                completed_routines=completed, routine_count=total, progress=progress,
                recent_observations=observations[:2], observation_count=len(observations),
                active_routine_count=len(groups))
