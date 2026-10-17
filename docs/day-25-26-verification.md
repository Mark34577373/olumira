# Days 25–26 completion report

Both milestones are implemented and verified locally. The user explicitly authorized
continuing through both days. No commit, push or deployment was performed.

## Day 25 completed — professional board editor

**Features:** profile/workspace board library with search/category/status filters,
real card counts, four editable starter templates, metadata/layout selection,
original built-in SVG pictures, card add/edit/duplicate/remove/reorder, draft visual
preview, native keyboard alternatives, pointer handles, persistent order, optimistic
versions, retained stale drafts, unsaved-change warnings, idempotent creation,
board duplication/archive/restore and preserved legacy browser choices.

**Main files:** `olumira/models.py`, `olumira/routes/communication.py`,
`services/communication.py`, `templates/communication.html`,
`templates/communication/editor.html`, `card_field.html`, `symbol.html`, `quick.html`,
`static/js/board-editor.js`, `static/css/style.css`, `olumira/__init__.py`,
`services/data_transfer.py` and `templates/base.html` navigation.

**Migration:** `0010_communication_boards.py`; additive board/card tables, foreign
keys, profile/workspace guards, ordering uniqueness and scope indexes. No original
rows/columns or browser custom choices are deleted or implicitly shared.

**Dependencies added:** none. Custom uploads remain disabled pending durable
private media storage. All built-in pictures are original project SVG markup.

**Tests/security/accessibility:** eight initial Day 25 service tests passed before
speech implementation continued. Final combined suite and browser evidence below
verify authorization, CSRF, validation, rollback, stale edits, foreign-card denial,
profile/workspace isolation, keyboard/pointer order, labels, touch and native forms.

**Local verification:** Communication → starter/Create board → edit cards/order →
Save → reload. Open board is a separate route with no editing controls. Manage from
the library to duplicate/archive/restore. Existing browser choices are under Quick
choices. See the [runbook](day-25-26-communication.md) for setup/rollback and limits.

**Suggested commit (not created):**
`Day 25: Build professional communication board editor`.

## Day 26 completed — independent communication and speech

**Features:** independent board opens in focus view by default; large labeled
picture cards, prominent Speak message, phrase tokens/written message, individual/
last-word removal, clear, stop/replay, speech on/off, local-only voice and conservative
rate selection, asynchronous voice loading, readable unsupported/error states,
focus/Escape/exit without losing the message, persistent saved phrases and manager
with edit/order/archive/restore, shared caregiver access and viewer use without edits.

**Main files:** shared service/routes/models plus `templates/communication/board.html`,
`phrases.html`, `static/js/communication-board.js`, stylesheet, demo script and tests.

**Migration:** `0011_communication_phrases.py`; additive explicit saved-phrase table
with profile/workspace foreign-key/trigger protection and scope/order index.

**Dependencies added:** none. Native Web Speech API is used; only voices identified
by the browser as local are offered. No external speech/AI service integration.

**Security/privacy:** active utterances stay only in page memory. Only explicitly
saved phrases are posted to the database; local storage holds namespaced speech
preferences, not messages. All persistence uses CSRF/current permissions/scopes,
transactions, idempotency and version checks. Cross-tab context binding prevents
saving phrases to a newly selected profile by mistake. Expired/revoked access is
rechecked by the server; known loss stops/clears/disables the page. No per-word
network requests or utterance analytics/logging are introduced.

**Accessibility:** native card activation speaks only on deliberate interaction,
not keyboard focus. Labels, visible focus, large targets, written alternatives,
non-color “Added” feedback, reduced motion, touch controls, native dialog and
Escape/exit are verified in the fictional browser flow. This is practical testing,
not formal WCAG certification.

**Known limitations:** audio/voice availability depends on the browser and OS;
headless Chromium had no actual local voice available. Speech lifecycle tests use
mocks and do not assert audible output. Install/enable an OS local voice and smoke
test in the intended device/browser. Drafts intentionally clear on reload/exit.
Offline writes are not queued; interrupted saves keep the draft and require retry.
Live PostgreSQL/Redis staging and formal accessibility certification remain outside
local evidence. Uploaded media is intentionally disabled, as allowed by the brief.

**Local verification:** Open board → I/want/water → Speak/Stop/Replay and settings
when a local voice exists → save phrase → reload → reuse phrase. Exit focus restores
normal navigation; Exit board returns to the library. A viewer can communicate but
cannot enter the editor/save phrases. See the runbook for the complete demo.

**Suggested commit (not created):**
`Day 26: Add visual communication and text-to-speech`.

## Actual final verification

| Executed command/check | Result |
|---|---|
| `venv/bin/python -m pytest -q` | **144 passed, 1 skipped, 18 subtests passed**, 294.34 seconds |
| Communication/persistence/authentication focused tests | **40 passed**, 68.71 seconds |
| `tests/browser/check_communication_boards.py` | **10 grouped checks passed**, 24 page/viewport combinations, no failures |
| `tests/browser/check_ui.py` | **62 checks passed**, 42 page/viewport combinations, no console errors |
| `tests/browser/check_workspaces.py` | **47 checks passed**, 42 page/viewport combinations, no failures |
| Three browser suites combined | **119 grouped checks**, **108 page/viewport combinations** |
| Populated 0009 → 0010 → 0011 migration | Original tables preserved; populated board/card preserved; repeat upgrade, integrity/FKs and model/schema comparison passed |
| PostgreSQL offline `flask db upgrade --sql` | Generated through 0011; three new tables and scope guards present; no live DB connection |
| `venv/bin/python -m pip check` | No broken requirements |
| `venv/bin/gunicorn --check-config app:app` | Passed |
| Compile app/services/scripts; `git diff --check` | Passed |
| Local `flask db current` | **0011 (head)** |
| Running preview and normal login smoke check | Verified preview login, focused board, “I want water,” no JavaScript errors, desktop/mobile; normal localhost login HTTP 200 |

The single skip requires a configured disposable `TEST_POSTGRES_URL`. Intermediate
fixture/regression-route failures were corrected and rerun; only successful final
runs are counted. A legacy browser-storage assertion was moved to the preserved
Quick choices route, rather than removed or weakened.

New backend tests cover card CRUD/order, templates, draft actions, duplicate/
archive/restore, repeated creation, strict input handling, escaping, foreign IDs,
viewer/CSRF denial, membership revocation, profiles/families, stale versions,
simultaneous edits, save rollback, phrase CRUD/order/archive/restore, repeated phrase
creation returning actual persisted data, stale context, scope and migration safety.

The browser reproduces the end-to-end fictional workflow, including verified owner,
caregiver, viewer and separate-family accounts; original pictures; keyboard and
real pointer reorder confirmed to change saved order; saved draft conflicts; phrase
building/removal/clear; local-voice filtering, rate/on-off/speak/stop/replay; explicit
save with interrupted-network retry; restored saved phrases; errors/unavailable and
asynchronously loaded voices; focus/Escape; native editor without JavaScript;
keyboard/touch; labels, sampled text contrast and reduced motion. New pages were
checked at 320/375/390/768/1024/1440px including landscape tablet, without overflow.
Desktop/mobile screenshots were visually inspected.

Fictional artifacts: `artifacts/day25-26/report.json`, editor/board width screenshots
and running-preview screenshots. Existing regression reports remain under
`artifacts/after-day21/` and `artifacts/days17-21/`. These folders are ignored.

## Actual local database and preview

The normal server was stopped before upgrade. A verified private backup is in:
`database/backups/pre-day25-26-20261017T152608Z.db` (ignored, not committed).
Every original row/column in **22 pre-existing tables** was compared after upgrade
and remained unchanged. SQLite integrity/foreign-key checks passed; head is 0011.
Normal local service restarted at **http://127.0.0.1:5000**.

The fresh fictional preview is **http://127.0.0.1:5054/auth/login**. It has editable
boards, saved phrases and prior routine demonstrations, verified through the normal
development outbox/token services. Credentials are kept in a private temporary file,
not this repository. `scripts/preview_routines.py --port 5054` recreates it in an
isolated temporary database; changes last until it stops. Earlier preview databases
were not reset. Real mail delivery was not configured or claimed.

## Remaining file inventory

New tests: `tests/test_communication.py`, `tests/test_communication_migration.py`,
`tests/browser/check_communication_boards.py`. Regression routes updated in
`tests/test_authentication.py`, `tests/test_workspaces.py`,
`tests/browser/check_ui.py` to continue exercising preserved browser choices.
Demo updated in `scripts/preview_routines.py`. Documentation updated in `README.MD`,
`docs/database-migration.md`, `docs/day-25-26-plan.md`,
`docs/day-25-26-communication.md` and this report.

No new production credentials, media service, analytics, dependency or hosting
configuration. Deployment/rollback instructions are in the runbook; deployment
remains a separate action and was not performed.
