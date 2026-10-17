"""Descriptive analytics, bounded inclusive local dates and shared report queries."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from flask import g
from sqlalchemy import select, func, case, exists, and_
from olumira.extensions import db
from olumira.models import (
    Routine,
    RoutineSession,
    Observation,
    CaregiverTask as Task,
    CaregiverHandoff as Handoff,
    HandoffRecipient as Recipient,
    utcnow,
)
from services.workspaces import require, scope
from services.journal import zone


@dataclass(frozen=True)
class Period:
    first: date
    last: date
    timezone: str
    lower: datetime
    upper: datetime
    grouping: str

    @property
    def label(self):
        return f"{self.first.isoformat()} through {self.last.isoformat()} ({self.timezone}, inclusive)"


def period(values):
    tz = zone(values.get("timezone"))
    today = datetime.now(tz).date()
    choice = values.get("period", "30") or "30"
    if choice in ["7", "30", "90"]:
        first = today - timedelta(days=int(choice) - 1)
        last = today
    elif choice == "custom":
        try:
            first = date.fromisoformat(values.get("from", ""))
            last = date.fromisoformat(values.get("to", ""))
        except ValueError:
            raise ValueError("Enter valid start and end dates.")
    else:
        raise ValueError("Choose 7, 30, 90 days or a custom date range.")
    if (
        first > last
        or (last - first).days > 365
        or first.year < 1900
        or last.year > 9998
    ):
        raise ValueError(
            "Choose an inclusive range of 1–366 days, from year 1900 through 9998."
        )
    grouping = values.get("grouping", "daily") or "daily"
    if grouping not in ["daily", "weekly"]:
        raise ValueError("Choose daily or weekly grouping.")
    return Period(
        first,
        last,
        str(tz),
        datetime.combine(first, time.min, tz).astimezone(timezone.utc),
        datetime.combine(last + timedelta(days=1), time.min, tz).astimezone(
            timezone.utc
        ),
        grouping,
    )


def scoped(model):
    return scope(model, g.owner_id)


def interval(column, p):
    return and_(column >= p.lower, column < p.upper)


def observation_query(p, category=""):
    query = select(Observation).where(
        scoped(Observation),
        Observation.archived_at.is_(None),
        interval(Observation.observed_at, p),
    )
    if category:
        query = query.where(Observation.category == category)
    return query


def pending():
    return exists().where(
        Recipient.handoff_id == Handoff.id, Recipient.acknowledged_at.is_(None)
    )


def count(model, *terms):
    return (
        db.session.scalar(
            select(func.count()).select_from(model).where(scoped(model), *terms)
        )
        or 0
    )


def buckets(p):
    rows = []
    day = p.first
    step = 7 if p.grouping == "weekly" else 1
    tz = zone(p.timezone)
    while day <= p.last:
        last = min(day + timedelta(days=step - 1), p.last)
        rows.append(
            dict(
                label=(
                    day.isoformat()
                    if step == 1
                    else f"{day.isoformat()} – {last.isoformat()}"
                ),
                lower=datetime.combine(day, time.min, tz).astimezone(timezone.utc),
                upper=datetime.combine(
                    last + timedelta(days=1), time.min, tz
                ).astimezone(timezone.utc),
            )
        )
        day = last + timedelta(days=1)
    return rows


def series(model, column, terms, p, slots):
    # One SQL grouping query per series. UTC boundaries are constructed using IANA
    # rules, so DST days are 23/25 hours on both SQLite and PostgreSQL.
    index = case(
        *[
            (and_(column >= b["lower"], column < b["upper"]), i)
            for i, b in enumerate(slots)
        ],
        else_=-1,
    )
    counts = dict(
        db.session.execute(
            select(index.label("bucket"), func.count())
            .select_from(model)
            .where(scoped(model), interval(column, p), *terms)
            .group_by(index)
        ).all()
    )
    return [counts.get(i, 0) for i in range(len(slots))]


def calculate(p, category=""):
    require("analytics.view")
    if len(category) > 60:
        raise ValueError("Shorten the category filter.")
    obs_terms = [Observation.archived_at.is_(None)]
    if category:
        obs_terms.append(Observation.category == category)
    stats = metric_counts(p, category)
    categories = db.session.execute(
        select(Observation.category, func.count())
        .where(scoped(Observation), *obs_terms, interval(Observation.observed_at, p))
        .group_by(Observation.category)
        .order_by(Observation.category)
    ).all()
    task_states = db.session.execute(
        select(Task.status, func.count())
        .where(scoped(Task))
        .group_by(Task.status)
        .order_by(Task.status)
    ).all()
    slots = buckets(p)
    routines = series(
        RoutineSession,
        RoutineSession.completed_at,
        [RoutineSession.status == "completed"],
        p,
        slots,
    )
    observations = series(Observation, Observation.observed_at, obs_terms, p, slots)
    chart = [
        dict(label=s["label"], routines=r, observations=o)
        for s, r, o in zip(slots, routines, observations)
    ]
    contributions = dict(
        observations_recorded=count(Observation, interval(Observation.created_at, p)),
        routine_runs_started=count(
            RoutineSession, interval(RoutineSession.started_at, p)
        ),
        handoffs_created=count(Handoff, interval(Handoff.created_at, p)),
    )
    acknowledgments = (
        db.session.scalar(
            select(func.count())
            .select_from(Recipient)
            .join(Handoff, Handoff.id == Recipient.handoff_id)
            .where(scoped(Handoff), interval(Recipient.acknowledged_at, p))
        )
        or 0
    )
    contributions["handoff_acknowledgments"] = acknowledgments
    # Historical eligible schedule occurrence/cancellation inventory is not
    # complete: occurrence rows exist only after launch. A launched-session
    # denominator would be misleading. Expose unavailable, never a fake percent.
    rate = dict(
        value=None,
        numerator=None,
        denominator=None,
        reason="Unavailable: schedule occurrences are stored only when launched. A complete historical inventory of eligible and canceled occurrences is not available; completed launches are not a valid denominator.",
    )
    return dict(
        stats=stats,
        categories=categories,
        task_states=task_states,
        chart=chart,
        chart_max=max([1] + routines + observations),
        contributions=contributions,
        completion_rate=rate,
        period=p,
        category=category,
        generated_at=utcnow(),
    )


DEFINITIONS = (
    (
        "Routine completions",
        "Completed guided routine sessions, counted once by their completion timestamp. Historical completed runs remain counted after a routine is archived. Legacy daily checklist ticks are a different record type and are excluded.",
    ),
    (
        "Observations",
        "Unarchived entries whose known observation timestamp falls in the range. Date-only entries are shown separately, with clock time unknown, and excluded from time-based charts. Category filters affect observations only. Documentation frequency is not a measure of progress.",
    ),
    (
        "Active routines",
        "Currently unarchived routine templates and checklist activities in this exact profile; a current snapshot, independent of the selected date range.",
    ),
    (
        "Completed tasks",
        "Tasks currently completed whose completion timestamp falls in the range. Reopened or canceled tasks are excluded; this is not a count of historical state transitions.",
    ),
    (
        "Pending handoffs",
        "Current handoffs with at least one intended recipient not yet acknowledged, including recipients who since left. This is a current snapshot, independent of the selected date range.",
    ),
    (
        "Care-team contributions",
        "Aggregate entries recorded, runs started, handoffs created and recipient acknowledgments during the range. No caregiver rankings or performance scores.",
    ),
    (
        "Date boundaries",
        "Start and through dates are inclusive in the chosen IANA timezone; queries use a half-open UTC interval. Weekly buckets begin on the selected start date. Zero bars mean no matching stored events; missing legacy times are never treated as zero events.",
    ),
)


def metric_counts(p, category=""):
    require("analytics.view")
    obs_terms = [Observation.archived_at.is_(None)]
    if category:
        obs_terms.append(Observation.category == category)
    stats = dict(
        routine_completions=count(
            RoutineSession,
            RoutineSession.status == "completed",
            interval(RoutineSession.completed_at, p),
        ),
        observations=count(
            Observation, *obs_terms, interval(Observation.observed_at, p)
        ),
        active_routines=count(Routine, Routine.archived_at.is_(None)),
        completed_tasks=count(
            Task, Task.status == "completed", interval(Task.completed_at, p)
        ),
        pending_handoffs=count(Handoff, pending()),
    )
    unknown = count(
        Observation,
        *obs_terms,
        Observation.observed_at.is_(None),
        Observation.date >= p.first.isoformat(),
        Observation.date <= p.last.isoformat(),
    )
    stats["date_only_observations"] = unknown
    return stats
