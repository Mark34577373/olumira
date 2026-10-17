# Days 23–24: scheduling and shared guided routines

The existing Flask/Jinja application now has a daily/seven-day routine calendar,
timezone-aware recurring rules, shared guided runs, and snapshot-based history.
No frontend framework, background scheduler or new dependency is required.

## Day 23 behavior

Open **Routines → a routine → Schedule routine**. The active workspace/profile
selects the routine and schedule scope. Switch profiles in the existing header;
workspace-level routines remain separate from care-profile routines. Rules support
one time, daily, selected weekdays and weekly on the start weekday, optional end
dates, and up to twelve active/paused schedules per routine. Different routines
and overlapping rules are allowed; identical absolute start times are marked
“Shared start time.” Exact duplicate rule definitions for a routine are rejected.
A live plain-language summary lets caregivers review their selection before saving.

**Routines → Schedule** offers date navigation, daily or seven-day views and an
explicit display timezone. Cards become a vertical daily list on narrow screens.
Dashboard upcoming cards show the next five actual occurrences within fourteen
days, ordered by absolute UTC time. Empty schedules do not fabricate activities.

IANA zones are validated with Python `zoneinfo` (existing `tzdata` dependency).
Rule dates/times are local wall-clock values; occurrence timestamps are UTC. The
server's local timezone is never used. Nonexistent spring-forward recurring times
are skipped; ambiguous autumn times use the first fold exactly once. A one-time
nonexistent time is rejected. These policies appear beside the calendar/form.
One-time rules must be future times. Recurring rules with an earlier start date
begin at the next matching future time; no backdated runs are generated. End dates
must follow the start and cannot already be past when creating/editing/resuming.

Schedule definitions use numbered revisions with half-open UTC validity windows.
Editing closes the old window at the save instant and creates a new definition.
Earlier generated calendar entries and already materialized occurrences are not
rewritten. Pause/end close the active window; resume creates a new revision.
Ending is terminal: create a new schedule if needed. Archive pauses active rules
inside the routine archive transaction; restore does not automatically resume them.

Calendar GETs generate bounded occurrences in memory (maximum fourteen days) and
never insert records. Each identity is SHA-256(revision ID + local date), with a
unique revision/date constraint. An occurrence is materialized only when starting
a scheduled run, inside the workspace write lock and transaction. Existing
occurrence snapshots always override regenerated calendar entries. Launches are
bounded to seven days before/fourteen days after today in the schedule's zone.
Inactive historical definitions and dates outside this launch window remain
viewable without a misleading start button. No unbounded queue or cron is needed.

## Day 24 behavior

Choose **Start or resume guided routine**, or **Start routine** from the calendar.
The dedicated player shows the profile, frozen title/instructions/icons, current
step, step count, real saved progress, previous/next links, complete/undo controls,
pause/resume and exit to dashboard. Guided and overview modes use ordinary links,
preserve progress and work without JavaScript. Essential global navigation stays
available. Finishing every step saves one completion and shows a calm summary.
Finished runs are read-only; start a fresh run explicitly from the source routine.

An ad-hoc routine has at most one unfinished run; a nullable unique active slot is
released only at completion. Each scheduled occurrence has at most one session,
including after completion. Random launch keys map every accepted launch intent
to the saved run, including requests that resumed an existing run. Retrying an old
launch after completion cannot accidentally create another run; a new form key
permits an explicit new ad-hoc run.

Each session freezes workspace/profile, profile display name, routine version,
title, description, icon/color and every ordered step. Template step edits/deletes
never change these records. Routine reassignment is refused once it has schedules,
legacy completion history or guided runs; duplicate for another profile instead.
History authorization uses the session's frozen association, never the current
routine template's association. Archiving keeps existing runs accessible and lets
caregivers finish them, while preventing new runs and future scheduling.

Step writes express **complete** or **undo**, never a blind toggle. Every mutation
carries a session version and a random action ID. Retried action IDs are checked
against actor/session/action/step and do not apply again. Stale forms show HTTP 409
with latest progress and clear review guidance. Workspace-first locking serializes
launches, schedule edits, membership changes and caregiver updates on SQLite and
PostgreSQL. Every mutation checks current membership again under that lock.
An optional ten-second visible-tab poll announces new saved progress and offers
an explicit refresh; it never replaces a focused step or replays a stale action.

Step completion stores caregiver/time; run activity records start, completion,
undo, pause, resume and finish, with names resolved only inside the authorized
workspace view. The detail shows the latest 100 actions. History is paginated at
20 runs, supports status/routine/date filters, and honors the active profile plus
an explicit date-filter timezone. Completed-session count and unfinished-run links
are separate from legacy daily checklist metrics. Dashboard queries use counts and
limits; they do not load the workspace's entire session history.

## Database and security

- `0008`: `routine_schedules`, `routine_schedule_revisions`, `routine_occurrences`.
- `0009`: `routine_sessions`, `routine_session_steps`, `routine_session_events`,
  `routine_launch_requests`.
- Additive tables only; no routine parent rebuild, deletion, reassignment or
  conversion of legacy completion dates into invented guided runs.
- Foreign keys, occurrence/session/active-slot uniqueness and supporting indexes.
- SQLite/PostgreSQL triggers reject routine/scope mismatches, snapshot changes,
  and updates/deletes to finished sessions/steps.
- Every new page remains behind verified authentication, current membership and
  selected profile scope. Caregivers can schedule/run; viewers can read only.
- All writes use the existing CSRF protection; no GET creates a session/occurrence.
- Existing no-store, CSP, rate-limit/authentication and sanitized error handling
  remain in force. No external visual assets, tracking, browser-storage progress,
  email credentials or synthetic production records are introduced.
- Legacy-only data transfer now checks head `0009` and refuses these new tables
  rather than silently dropping scheduling/session data.

## Local setup, staging and rollback

No new environment variables. `APP_TIMEZONE` remains the dashboard/default display
zone; individual schedules carry their own IANA timezone. Existing stable secret,
DB URL, verified login, Redis and SMTP requirements remain unchanged. Email delivery
configuration is independent of these milestones; development outbox is not proof
of a delivered message.

1. Stop writers and take a private, verified database backup (including independent
   mail encryption key backup using the existing operations procedure).
2. Review the additive migration SQL and run
   `venv/bin/python -m flask --app app db upgrade` against the intended database.
3. Restart the existing `gunicorn app:app` service or local Flask server. Startup
   does not migrate automatically. Keep the same secret/mail keys.
4. Verify login, profile switching, daily and weekly schedules, IANA timezone/DST,
   simultaneous caregiver actions, pause/reload/resume, completion/history,
   template-edit snapshots, viewer denials and a separate workspace's 404s.
5. Check the DB revision is `0009`, foreign keys/integrity, request logs (without
   submitted private content), mobile layout and CSP/static assets.

New assets: `routine-schedule.js`, `routine-player.js` and existing stylesheet
extensions. Render needs no additional worker/process for these features. Do not
push or deploy automatically. PostgreSQL/Redis staging is still an explicit
operational gate when those services are available; SQLite tests and offline SQL
are not a live PostgreSQL concurrency benchmark.

Both downgrades intentionally refuse data loss. To roll back, quiesce writers,
retain a current incident snapshot, restore a verified pre-upgrade backup and
matching prior application version/keys together. A pre-upgrade backup excludes
subsequent real activity: review and reconcile any later records before rollback.

## Repeatable fictional demonstration

For a clickable local preview, run `venv/bin/python scripts/preview_routines.py`
and open http://127.0.0.1:5053/auth/login. It prints the path to a private file with
fictional owner/caregiver/viewer credentials, seeds weekday schedules and paused
3/5-step runs, and never opens the real database. Changes last until it stops.

Use an isolated disposable database. The browser runner below seeds verified
fictional owner, caregiver, viewer and separate-family accounts; no real email is
sent and production authorization is not bypassed. It performs this complete flow:

1. Select Fictional Fern; create a five-step morning routine and reorder a step.
2. Schedule the routine on weekdays at 07:15 UTC; inspect day and week views.
3. Launch a scheduled run, complete/undo a step, then save three of five steps.
4. Pause, reload, and let another authorized caregiver resume it.
5. Observe shared-progress notification; submit a stale form to see safe conflict
   handling, then finish the two remaining steps with current versions.
6. Open history, filter completed runs, and inspect caregiver attribution.
7. Edit the template; confirm completed snapshots keep original labels/order.
8. Confirm the viewer has no write controls and another family gets 404.
9. Repeat essential controls without JavaScript, by keyboard, and with touch.

Commands:

```sh
venv/bin/python -m pytest -q
venv/bin/python tests/browser/check_guided_routines.py
venv/bin/python tests/browser/check_routine_builder.py
venv/bin/python tests/browser/check_ui.py
venv/bin/python tests/browser/check_workspaces.py
venv/bin/python -m pip check
venv/bin/gunicorn --check-config app:app
```

Browser runners require loopback sockets and Chromium. They emit fictional-only
screenshots and reports to ignored `artifacts/` directories. No production data,
raw tokens or cookies are part of those artifacts.

## Limits and suggested commits

Recurrence deliberately excludes intervals/monthly rules, durations, reminders and
notifications. Overlap means equal start times because routines have no duration.
There is no offline write queue; network failures must be retried with the saved
form, and are never shown as successful progress. Native form submissions provide
server-confirmed feedback; optional polling is eventual, not a WebSocket stream.
History uses the frozen title; caregiver names reflect their current display name.
The workspace write lock favors correctness over simultaneous writes within one
family; no performance benchmark is claimed. Formal WCAG certification and live
PostgreSQL/Redis deployment verification remain outside local evidence.

Suggested commits (not created):
`Day 23: Add recurring schedules and routine calendar`
and `Day 24: Add shared guided routines and immutable completion history`.

The separate verification report records only commands actually executed.
