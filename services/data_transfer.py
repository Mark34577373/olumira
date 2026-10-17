"""Explicit, backed-up transfers. Never reset or overwrite a destination."""

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from sqlalchemy import inspect, select, text
from olumira.extensions import db
from olumira.models import (
    Owner,
    Routine,
    Observation,
    RoutineCompletion,
    User,
    AuthSession,
    AccountToken,
    EmailOutbox,
    FamilyWorkspace,
    WorkspaceMembership,
    CareProfile,
    WorkspaceInvitation,
    AuditEvent,
    RoutineStep,
    RoutineCompletionSnapshot,
    RoutineSchedule,
    RoutineScheduleRevision,
    RoutineOccurrence,
    RoutineSession,
    RoutineSessionStep,
    RoutineSessionEvent,
    RoutineLaunchRequest,
    CommunicationBoard,
    CommunicationCard,
    SavedCommunicationPhrase,
    CommunicationPreference,
    FavoriteCommunicationCard,
    FavoriteCommunicationPhrase,
    CaregiverTask,
    CaregiverHandoff,
    HandoffRecipient,
    HandoffTask,
    CalendarEvent,
    ReminderPreference,
    Resource,
    ResourceBookmark,
    DashboardPreference,
    OnboardingState,
)

MODELS = (Owner, Routine, Observation, RoutineCompletion)
LEGACY_COLUMNS = {
    "owners": ("id", "created_at"),
    "routines": ("id", "owner_id", "name", "category"),
    "observations": ("id", "owner_id", "activity", "date", "notes", "mood", "tags"),
    "routine_completions": ("routine_id", "completion_date"),
}


def backup_sqlite(source, backup):
    source, backup = Path(source).resolve(), Path(backup).resolve()
    if not source.is_file() or source == backup:
        raise ValueError(
            "Source must be an existing SQLite file distinct from the backup"
        )
    backup.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids replacing any earlier recovery copy.
    with backup.open("xb"):
        pass
    backup.chmod(0o600)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(backup)) as dest:
            src.backup(dest)
    return backup


def read_snapshot(path):
    """Validate without returning record values in error messages."""
    with closing(
        sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.row_factory = sqlite3.Row
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Source integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Source has invalid foreign-key relationships")
        records = {}
        for model in MODELS:
            table = model.__table__
            columns = {
                r["name"]
                for r in connection.execute(f"PRAGMA table_info({table.name})")
            }
            baseline = set(LEGACY_COLUMNS[table.name])
            if columns not in (
                baseline,
                baseline | {"workspace_id"},
                baseline | {"workspace_id", "profile_id"},
                set(table.columns.keys()),
            ):
                raise ValueError("Source schema does not match the supported baseline")
            records[table.name] = [
                dict(r)
                for r in connection.execute(
                    f'SELECT {",".join(LEGACY_COLUMNS[table.name])} FROM {table.name}'
                )
            ]
    owners = {r["id"] for r in records["owners"]}
    routines = {r["id"] for r in records["routines"]}
    for model in MODELS:
        table = model.__table__
        seen = set()
        for record in records[table.name]:
            key = tuple(record[c.name] for c in table.primary_key)
            if key in seen or any(v is None for v in key):
                raise ValueError("Source contains duplicate or missing primary keys")
            seen.add(key)
            if any(
                record[c.name] is None
                for c in table.columns
                if not c.nullable and c.name in record
            ):
                raise ValueError("Source has missing required values")
            if (
                "owner_id" in record
                and record["owner_id"] is not None
                and record["owner_id"] not in owners
            ):
                raise ValueError("Source contains an unknown workspace relationship")
            if (
                table.name == "routine_completions"
                and record["routine_id"] not in routines
            ):
                raise ValueError("Source contains an orphan completion")
            for field in ("date", "completion_date", "created_at"):
                if field in record:
                    try:
                        valid = (
                            date.fromisoformat(record[field]).isoformat()
                            == record[field]
                        )
                    except (ValueError, TypeError):
                        valid = False
                    if not valid:
                        raise ValueError("Source contains an invalid calendar date")
    return records


def transfer_sqlite(source, backup):
    """Back up first; import an immutable snapshot in one destination transaction."""
    snapshot = backup_sqlite(source, backup)
    records = read_snapshot(snapshot)
    with closing(sqlite3.connect(snapshot)) as source_connection:
        tables = {
            r[0]
            for r in source_connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for table in (
            "users",
            "auth_sessions",
            "account_tokens",
            "email_outbox",
            "family_workspaces",
            "workspace_memberships",
            "care_profiles",
            "workspace_invitations",
            "audit_events",
            "routine_steps",
            "routine_completion_snapshots",
            "routine_schedules",
            "routine_schedule_revisions",
            "routine_occurrences",
            "routine_sessions",
            "routine_session_steps",
            "routine_session_events",
            "routine_launch_requests",
            "communication_boards",
            "communication_cards",
            "saved_communication_phrases",
            "communication_preferences",
            "favorite_communication_cards",
            "favorite_communication_phrases",
            "caregiver_tasks",
            "caregiver_handoffs",
            "handoff_recipients",
            "handoff_tasks",
            "calendar_events",
            "reminder_preferences",
            "resource_bookmarks",
            "dashboard_preferences",
            "onboarding_states",
            "user_preferences",
            "notifications",
            "notification_preferences",
            "data_exports",
            "deletion_requests",
        ):
            if (
                table in tables
                and source_connection.execute(
                    f"SELECT 1 FROM {table} LIMIT 1"
                ).fetchone()
            ):
                raise ValueError(
                    "Legacy-only transfer refuses account/session records; use an account-aware migration"
                )
        columns = {
            row[1] for row in source_connection.execute("PRAGMA table_info(routines)")
        }
        if (
            "is_checklist" in columns
            and source_connection.execute(
                "SELECT 1 FROM routines WHERE is_checklist=0 OR description<>'' OR icon<>'sun' OR color<>'sage' OR archived_at IS NOT NULL OR version<>1 OR created_by IS NOT NULL OR created_at IS NOT NULL OR updated_at IS NOT NULL LIMIT 1"
            ).fetchone()
        ):
            raise ValueError(
                "Legacy transfer refuses rich routine metadata; use a complete database migration"
            )
        observation_columns = {
            row[1]
            for row in source_connection.execute("PRAGMA table_info(observations)")
        }
        if (
            "category" in observation_columns
            and source_connection.execute(
                "SELECT 1 FROM observations WHERE category<>'General notes' OR author_id IS NOT NULL OR observed_at IS NOT NULL OR timezone IS NOT NULL OR created_at IS NOT NULL OR updated_at IS NOT NULL OR archived_at IS NOT NULL OR version<>1 OR session_id IS NOT NULL OR task_id IS NOT NULL LIMIT 1"
            ).fetchone()
        ):
            raise ValueError(
                "Legacy transfer refuses rich observation metadata; use a complete database migration"
            )
        resource_rows = None
        if "resources" in tables:
            fields = [
                column.name
                for column in Resource.__table__.columns
                if column.name not in ["created_at", "updated_at"]
            ]
            resource_rows = [
                tuple(row)
                for row in source_connection.execute(
                    "SELECT " + ",".join(fields) + " FROM resources ORDER BY id"
                )
            ]
            if source_connection.execute(
                "SELECT 1 FROM resources WHERE created_at<>updated_at LIMIT 1"
            ).fetchone():
                raise ValueError(
                    "Legacy transfer refuses edited resource metadata; use a complete migration"
                )
    with db.engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(
                text(
                    "LOCK TABLE owners, routines, observations, routine_completions, users, auth_sessions, account_tokens, email_outbox, family_workspaces, workspace_memberships, care_profiles, workspace_invitations, audit_events, routine_steps, routine_completion_snapshots, routine_schedules, routine_schedule_revisions, routine_occurrences, routine_sessions, routine_session_steps, routine_session_events, routine_launch_requests, communication_boards, communication_cards, saved_communication_phrases, communication_preferences, favorite_communication_cards, favorite_communication_phrases, caregiver_tasks, caregiver_handoffs, handoff_recipients, handoff_tasks, calendar_events, reminder_preferences, resources, resource_bookmarks, dashboard_preferences, onboarding_states, user_preferences, notifications, notification_preferences, data_exports, deletion_requests IN ACCESS EXCLUSIVE MODE"
                )
            )
        elif connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            raise ValueError("Unsupported destination database")
        inspector = inspect(connection)
        if (
            "alembic_version" not in inspector.get_table_names()
            or connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            != "0021"
        ):
            raise ValueError(
                "Destination must be migrated to the supported revision first"
            )
        for model in (
            *MODELS,
            User,
            AuthSession,
            AccountToken,
            EmailOutbox,
            FamilyWorkspace,
            WorkspaceMembership,
            CareProfile,
            WorkspaceInvitation,
            AuditEvent,
            RoutineStep,
            RoutineCompletionSnapshot,
            RoutineSchedule,
            RoutineScheduleRevision,
            RoutineOccurrence,
            RoutineSession,
            RoutineSessionStep,
            RoutineSessionEvent,
            RoutineLaunchRequest,
            CommunicationBoard,
            CommunicationCard,
            SavedCommunicationPhrase,
            CommunicationPreference,
            FavoriteCommunicationCard,
            FavoriteCommunicationPhrase,
            CaregiverTask,
            CaregiverHandoff,
            HandoffRecipient,
            HandoffTask,
            CalendarEvent,
            ReminderPreference,
            ResourceBookmark,
            DashboardPreference,
            OnboardingState,
        ):
            if connection.execute(select(model.__table__).limit(1)).first() is not None:
                raise ValueError("Destination is not empty; transfer refused")
        if resource_rows is not None:
            expected = [
                tuple(row)
                for row in connection.execute(
                    select(*[Resource.__table__.c[key] for key in fields]).order_by(
                        Resource.id
                    )
                )
            ]
            if resource_rows != expected:
                raise ValueError(
                    "Legacy transfer refuses changed curated resources; use a complete database migration"
                )
        for model in MODELS:
            table = model.__table__
            rows = records[table.name]
            if rows:
                payload = (
                    [dict(row, created_at=None, updated_at=None) for row in rows]
                    if table.name == "routines"
                    else rows
                )
                connection.execute(table.insert(), payload)
            actual = [dict(r) for r in connection.execute(select(table)).mappings()]
            normalize = lambda values: sorted(
                tuple(r[c] for c in LEGACY_COLUMNS[table.name]) for r in values
            )
            if normalize(actual) != normalize(rows):
                raise ValueError(
                    "Destination verification failed; transaction rolled back"
                )
        if connection.dialect.name == "postgresql":
            for name in ("routines", "observations"):
                connection.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {name}"
                    )
                )
    return {name: len(rows) for name, rows in records.items()}
