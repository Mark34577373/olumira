# Days 27–28 completion and verification

Both milestones are implemented and verified locally. The user's instruction to
continue through both overrides the source prompt's review stop. No commit, push,
production deployment or external notification was performed.

## Day 27 completed

- Server-persisted profile communication settings: card sizes/layouts, label
  placement/visibility, symbols, speech defaults/rate/voice, simplified mode,
  contrast, reduced motion and default board. Safe defaults and live draft preview.
- Default-board shortcut, active-board switching and profile selection that opens
  the correct default/favorites/library while clearing transient words.
- Persistent card/phrase favorite references, duplicate prevention, removal/order,
  focused favorites view, archived-source handling and stale-source fingerprints.
- Cross-device caregiver preferences, unavailable local-voice fallback, readable
  written communication, retained message when toggling simpler/full controls.
- Current workspace/profile/role authorization, CSRF, input validation and version
  conflicts; viewers use communication without managing shared preferences.

Main files: `services/communication_preferences.py`,
`olumira/routes/communication.py`, `templates/communication/settings.html`,
`favorites.html`, `select_profile.html`, updated `board.html`/library,
`static/js/communication-preferences.js`, updated `communication-board.js`, models,
CSS, profile switching, navigation and permission hooks.

Migration **0012** adds profile preferences and card/phrase reference favorites,
with foreign keys, uniqueness and scope guards. No dependencies added.

Tests: the first three focused Day 27 tests passed before Day 28 continued. Final
focused/full/browser evidence below additionally verifies favorite phrase ordering,
source-change fingerprints, cross-profile/default isolation and viewer denial.

Local verification: select a profile → Communication → Display & speech preferences
→ save a default/layout → Manage favorites → reorder → Open my communication.
Repeat in another browser/caregiver session; switch profiles and verify a fresh,
correctly scoped communication experience.

Suggested commit (not created):
`Day 27: Add personalized communication and accessibility`.

## Day 28 completed

- Care team responsibilities: profile association, description, validated active
  caregiver/unassigned assignment, priority, due date/IANA zone and routine link.
- Versioned edits/reassignment and explicit To do/In progress/Completed/Canceled
  transitions, timestamps/actor, reopening and idempotent completion/creation.
- My/all/upcoming/overdue/completed views, assignee/status/profile filters,
  pagination, actual assignee display and inactive-member guidance.
- Immutable handoff summary/profile/recipient snapshot, up to ten task links,
  optional routine/original observation references and recipient-specific
  acknowledgments. Team recipients have separate records; removed recipients
  remain named/pending, never falsely acknowledged.
- Filtered handoff history, scoped private observation detail and safe user-facing
  activity from existing audit events. No observation notes/phrase text in timeline
  previews and no duplicate event store.
- Real dashboard responsibilities, pending inbox count/links and recent activity.
  Central care read/manage/acknowledge permissions; viewer read-only behavior.

Main files: `services/care_coordination.py`, `olumira/routes/care.py`,
`templates/care/` (navigation, task list/editor/detail, handoff list/editor/detail,
activity and private observation), updated dashboard service/template, shared
models/permissions/navigation/CSS and demo script.

Migration **0013** adds tasks, immutable handoffs, recipient acknowledgments and
handoff/task links. Guards enforce profile/reference/assignment scope and history
immutability. No dependencies or environment variables added.

Local verification: Care team → create/assign a routine-linked task → another
caregiver completes it → create a task/observation-linked handoff → intended
recipient acknowledges → inspect history, dashboard and safe shared activity.

Suggested commit (not created):
`Day 28: Build shared caregiver workflows and handoffs`.

## Commands actually executed

| Check | Final result |
|---|---|
| `venv/bin/python -m pytest -q` | **155 passed, 1 skipped, 18 subtests passed**, 333.03 seconds |
| Personalization + coordination + populated migration focused suite | **11 passed**, final expanded run 30.73 seconds |
| `tests/browser/check_personalized_care.py` | **6 grouped workflow checks**, **55 page/viewport combinations**, no failures |
| `tests/browser/check_communication_boards.py` | **10 grouped checks**, **24 page/viewport combinations**, no failures |
| `tests/browser/check_ui.py` | **62 checks**, **42 page/viewport combinations**, no failures or console errors |
| Three browser suites combined | **78 grouped checks**, **121 page/viewport combinations** |
| Populated 0011 → 0012 → 0013, repeated upgrade | Existing data and populated preferences/favorites preserved; model/schema comparison, integrity and FKs passed |
| PostgreSQL offline `flask db upgrade --sql` | SQL through 0013 generated, seven new tables and reference/history/assignee guards present; no live connection |
| `venv/bin/python -m pip check` | No broken requirements |
| `venv/bin/gunicorn --check-config app:app` | Passed |
| Compile app/services/scripts; `git diff --check` | Passed |
| Local `flask db current` | **0013 (head)** |
| Final running preview smoke | Verified login, profile default/layout, matching favorites refresh identity, task assignee list, recipient-specific pending dashboard, handoff/activity; normal localhost login HTTP 200 |

The skip requires a disposable `TEST_POSTGRES_URL`, which is not configured. Live
PostgreSQL/Redis staging and performance benchmarks are not claimed. A legacy
architecture assertion was updated to expect the new protected care blueprint;
intermediate failures were corrected and successful final runs are reported above.

Focused tests include settings/default persistence after login, invalid options and
invisible-card rejection, unique/reference favorites, card and phrase ordering,
archive/source version changes, viewer/foreign-profile denial, task creation/edit/
reassignment, inactive/viewer assignee rejection, transition/reopen/time attribution,
CSRF, IANA/DST validation, linked-reference scope, rollback, pending/acknowledged
history, recipient-only acknowledgment/retry, team membership snapshots/removal,
concurrent task edits/completion and concurrent acknowledgment deduplication.

The new fictional browser flow creates/configures a profile board, favorites cards
and a phrase, changes size/contrast/motion/layout/speech/defaults, loads the same
preferences in a fresh caregiver browser, switches profiles without leaking an
active message, assigns/completes/reassigns a task, rejects a retained stale draft,
completes a linked guided routine, shares/acknowledges a linked handoff and checks
real pending counts and private observation navigation. Viewer and unrelated-family
denials are exercised. Eleven pages were checked at 320/390/768/1024/1440px including
landscape tablet, with labeled visible controls and no horizontal overflow; native
forms and touch/simple-mode message preservation passed. Desktop/mobile screenshots
were visually inspected. Existing board/UI suites also sampled text contrast,
keyboard focus, local-voice errors/unsupported speech and reduced motion.

Speech APIs are mocked in automation. Audible output and identical voices across
devices are not asserted; the headless live preview has no installed local voice.
Written communication remains functional. This is practical accessibility testing,
not formal WCAG certification.

## Actual local data and interactive preview

The real local server was stopped before backup/upgrade. Private verified backup:
`database/backups/pre-day27-28-20261017T191822Z.db` (ignored, not committed).
All original rows/columns in **25 pre-existing tables** were compared after upgrade
and remained unchanged. SQLite integrity/foreign keys passed; head is 0013.
The normal service is running at **http://127.0.0.1:5000**.

Fresh fictional preview: **http://127.0.0.1:5055/auth/login**. It uses a separate
temporary database and normal verified accounts. It contains Fictional Fern's
server preferences/default/favorite cards, saved phrases, guided routines, tasks
assigned to Fictional Sage and pending handoffs. Private demo credentials are in
the temporary file printed by `scripts/preview_routines.py --port 5055`; no passwords
are stored here. Preview changes last until the process stops. Earlier shared
preview databases were not reset. Actual email delivery was not configured or claimed.

Fictional screenshots/reports: ignored `artifacts/day27-28/`,
`artifacts/day25-26/` and `artifacts/after-day21/`.

## Limits and operations

- Workspace-wide care remains distinct from each selected profile; “All authorized”
  lists mean all tasks for that selected context, not an implicit cross-profile mix.
- No advanced/email notifications; in-app pending states are provided, with broader
  notifications deferred to Day 38 as allowed by the brief.
- Local voice availability, device audio, live PostgreSQL/Redis behavior and formal
  accessibility certification need their stated environment/manual checks.
- Bounded board/favorite/task/handoff/reference lists are documented in the runbook.
  Offline writes are not queued; forms show confirmed saves/errors. Handoff history
  is immutable; retention/export needs review before exceeding its stated cap.
- Custom uploaded media remains disabled pending durable private object storage.

Setup, scope semantics, history behavior, migration/rollback commands and repeatable
fictional demo are in [the runbook](day-27-28.md). Other updated files include
`README.MD`, `docs/database-migration.md`, `services/data_transfer.py`,
`scripts/preview_routines.py`, `tests/test_architecture.py` and the communication
browser regression's intentional server-preference refresh expectation. New tests:
`test_personalization.py`, `test_care_coordination.py`,
`test_days27_28_migration.py`, `browser/check_personalized_care.py`.
