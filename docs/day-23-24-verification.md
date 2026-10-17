# Days 23–24 completion and verification

Both milestones are implemented locally. No commit, push, production migration or
deployment was performed. Prior staged Day 22 work remains staged; new changes are
available for review separately.

## Implemented outcome

**Day 23:** one-time, daily, selected-weekday and weekly schedules; optional end
dates and multiple rules; IANA timezone conversion; deliberate DST gap/fold policy;
daily/seven-day responsive calendar, date navigation and active-profile context;
future-only revisioned edits, pause/resume/end, archive safety; duplicate rule
rejection and visible equal-start overlaps; stable occurrence identities without
GET writes; real upcoming dashboard cards.

**Day 24:** guided and overview modes; large visual steps and instructions;
previous/next, complete/undo, saved progress, pause/reload/resume and exit; friendly
completion summary; frozen template/profile/step snapshots; caregiver attribution;
versioned desired-state actions, idempotent launch/action retries and serialized
concurrent writes; visible-tab shared-update notice; bounded, filtered history;
separate legacy-checklist/guided-run metrics; viewer read-only access and strict
workspace/profile isolation.

Detailed semantics, demo, limits and deployment/rollback:
[Days 23–24 runbook](day-23-24-routines.md).

## Actual checks executed

| Command/check | Result |
|---|---|
| `venv/bin/python -m pytest -q` | **131 passed, 1 skipped, 18 subtests passed**, 265.10 seconds |
| New scheduling/session/migration focused suite | **22 passed, 13 subtests passed** |
| `tests/browser/check_guided_routines.py` | **12 grouped checks passed**, **48 page/viewport combinations**, no failures |
| `tests/browser/check_routine_builder.py` | **28 checks passed**, including 18 page/viewport combinations |
| `tests/browser/check_ui.py` | **62 checks passed**, including 42 page/viewport combinations; no console errors |
| `tests/browser/check_workspaces.py` | **47 checks passed**, including 42 page/viewport combinations |
| All four browser runners combined | **149 checks**, **150 page/viewport combinations** |
| `venv/bin/python -m pip check` | No broken requirements |
| `venv/bin/gunicorn --check-config app:app` | Passed |
| Compile app/services; `git diff --check` | Passed |
| PostgreSQL offline `flask db upgrade --sql` | Generated 0001–0009; all seven new tables and snapshot guards present; no live connection |
| Local `flask db current` | **0009 (head)** |

The skipped test requires an explicitly configured disposable `TEST_POSTGRES_URL`.
No live PostgreSQL/Redis staging verification or performance benchmark is claimed.
No new package dependency was introduced. Existing production configuration and
previously documented dependency findings still apply.

Backend cases include recurrence combinations, UTC/local date boundaries, DST gaps
and first folds, malformed dates/zones/rules, duplicates, overlaps, stale schedule
edits, pause/resume/end, preserved revision windows, unchanged materialized times,
GET idempotency, scheduled/ad-hoc launch uniqueness, replay after completion,
explicit new runs, desired-state undo, pause write denial, stale caregiver forms,
concurrent caregiver launches/steps, immutable finished history, template edits,
archive/restore, reassign prevention, viewer/CSRF denials, family/profile isolation,
revoked membership, filtered history and partial-failure rollback.

Browser cases perform the complete fictional five-step/profile/reorder/weekday
schedule/three steps/pause/other-caregiver resume/stale conflict/finish/history flow.
They also verify snapshots after edits, role/family isolation, native no-JavaScript
controls, touch pause/resume/mode switch, keyboard controls, labels, sampled text
contrast and reduced motion. New pages were checked at 320, 375, 390, 768, 1024 and
1440 pixels with no horizontal overflow. Desktop and mobile screenshots were
visually inspected. This is practical accessibility evidence, not certification.

Reports and fictional screenshots are in ignored `artifacts/day23-24/`,
`artifacts/day22/`, `artifacts/after-day21/` and `artifacts/days17-21/`.
Only successful final runs are counted above. Intermediate test failures were
corrected and rerun; no failed check is counted as a pass.

## Local data migration and interactive preview

The actual local server was stopped before backup/migration. Private backup:
`database/backups/pre-day23-24-20261017T145912Z.db` (ignored; not committed).
The backup was compared against the source, then all rows/all original columns in
**15 pre-existing tables** were compared after upgrade. They were unchanged.
SQLite integrity and foreign-key checks passed; migration head is `0009`.
The normal local service was restarted on **http://127.0.0.1:5000**.
A live browser check confirmed its login returns HTTP 200 and the new preview
accepts verified login, displays paused 3/5 progress, schedule and history, with no
JavaScript errors. A final model/schema comparison also passed after formatting.

An additional **http://127.0.0.1:5053/auth/login** preview uses an isolated temporary
database with fictional owner/caregiver/viewer accounts verified through the
existing encrypted development outbox/token service. It contains weekday schedules
and paused runs with three of five steps saved. `scripts/preview_routines.py` can
recreate it. It writes credentials to a private local temporary file and prints
that file's path; no credentials are stored in this repository/report. Preview
changes last until that process stops. Existing preview databases were not reset.

Production email delivery was not configured or claimed. These preview accounts
allow reviewing the new UI without waiting for real email delivery.

## Files changed for Days 23–24

- Models/migrations: `olumira/models.py`,
  `migrations/versions/0008_schedules.py`,
  `migrations/versions/0009_guided_sessions.py`.
- Services: new `services/routine_scheduling.py`, `services/routine_sessions.py`;
  updated `services/routine_builder.py`, `services/routines.py`,
  `services/dashboard.py`, `services/data_transfer.py`.
- Routes/permissions: `olumira/routes/routines.py`, `olumira/__init__.py`.
- Views: new `templates/routines/calendar.html`, `schedule.html`, `player.html`,
  `history.html`, `navigation.html`; updated `sequence.html`,
  `templates/routines.html`, `templates/dashboard.html`.
- Assets: new `static/js/routine-schedule.js`, `routine-player.js`;
  updated `static/css/style.css`.
- Tests/demo: `tests/test_routine_scheduling_sessions.py`,
  `tests/test_routine_schedule_migration.py`,
  `tests/browser/check_guided_routines.py`, `scripts/preview_routines.py`.
- Documentation: `README.MD`, `docs/database-migration.md`, this verification
  report and `docs/day-23-24-routines.md`.

Suggested commits, not created:
`Day 23: Add recurring schedules and routine calendar`;
`Day 24: Add shared guided routines and immutable completion history`.
