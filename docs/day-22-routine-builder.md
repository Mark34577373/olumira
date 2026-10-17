# Day 22: premium routine builder

Day 22 implementation is complete locally; verification results are recorded below. Days 23 (scheduling) and 24 (guided sessions) have not begun; the
current master prompt requests review between stages. No commit, push or deployment
is automatic. The original [inspection and implementation plan](day-22-implementation-plan.md)
records the intended separation between templates, schedules and execution history.

## Implemented experience

The Routines page is a visual library with a scoped profile selector in the existing
horizontal context bar, search, category and active/archived filters, 24-card
pagination, colors, icons and sequence previews. Owner/caregiver controls allow
editing, copying to an authorized profile, archiving and restoring. Viewers can read
sequences but cannot modify them, including through direct HTTP requests.

The builder provides a live preview, routine name/description/category/profile,
built-in SVG icon/color choices, and 1–30 ordered steps. Step cards support title,
optional instructions/icon, insertion/removal, keyboard Move up/Move down controls,
and pointer/touch dragging by a visible handle. Optional details collapse to keep
long mobile routines manageable. Native HTML controls also add/reorder/remove draft
steps with JavaScript disabled; those draft requests never save the database.
The live preview itself requires JavaScript. Save and Cancel remain ordinary links
and CSRF-protected forms. Unsaved-change warnings require JavaScript and browser
support; they are not a data-persistence mechanism.

Five optional sequence templates (morning, school, bedtime, packing a bag and
preparing for an activity) open editable drafts. They are copied only when saved.
The original daily checklist shortcuts remain available, alongside separate
personal sequences. The library has working View sequence links; it does not show
an inactive/fake guided Start button. Scheduling and persistent guided execution
belong to the next two stages.

The dashboard keeps actual daily checklist completion counts and shows a separate
count and bounded preview of personal routine sequences. It never treats saved
steps as completed steps. Profile overviews distinguish daily checklists from
sequences and avoid links that would open a different, unselected profile's scope.

## Models, migration and history

Migration **0007** extends Routine with description, allowlisted icon/color,
archive time, template version, daily-checklist classification, creator and UTC
metadata. It adds:

- `RoutineStep`: opaque ID, routine reference, ordered position, title, instructions,
  icon and timestamps; unique routine/position and nonnegative position constraint.
- `RoutineCompletionSnapshot`: original completion key, frozen label/category and
  workspace/profile association, source marker and capture time. It references the
  original completion through a composite foreign key.

The migration adds columns and tables without rebuilding routine parent tables.
Every existing routine becomes a one-step sequence while keeping its original ID,
name, scope, category and completion dates. Unknown legacy ownership remains
quarantined. Old creator and creation/update timestamps remain unknown; no historical
caregiver or original creation time is invented. Legacy names longer than the new
80-character form limit remain intact in text columns. New/edited titles are
validated to the new bound.

Existing completion snapshots are explicitly marked `source=migration`: the label
was captured during adoption, not proven to be the exact label on the original
completion date. New daily-checklist completions capture the known label and scope
at completion. No fictional historical step sessions are generated. Editing steps
or names and archiving do not rewrite these snapshots.

A routine with completion history cannot be reassigned to another profile; the
caregiver is guided to duplicate it instead. This prevents an old completion from
appearing as work performed for a different person. Fresh sequences may move to
another authorized profile within the workspace. Later guided sessions will need
independent immutable snapshot scope, as documented in the plan.

Public deletion now means archive, including the old delete URL. Restoring is
explicit, and archived routines cannot be edited or completed until restored.
Completion history is retained. Intentional “undo today's daily checklist” remains
the pre-existing daily toggle behavior; it removes that day's completion and its
associated snapshot, not an unrelated historical session.

## Transactions and concurrency

The existing workspace-first lock order is retained. All new mutations repeat
current membership/capability checks and query routines through the authorized
workspace and selected profile. Submitted profiles are separately validated against
the active workspace, and submitted existing step IDs must belong to the routine
being edited. Browser IDs never grant access.

A complete routine/step save is one transaction. Step positions are first moved
above the old/new range, flushed, and then assigned their final positions, avoiding
intermediate uniqueness violations during swaps. Deletions and inserts share that
transaction. Failures roll back metadata, steps and audit events together.

Every template change increments a version. Stale edits and archive/restore actions
return 409; editor conflicts retain the submitted draft and offer the latest saved
version in a new tab for comparison. The old edit/delete paths now require their
version as well, closing a stale-client bypass. Older forms without a version must
reload rather than silently overwrite new work. Duplication creates fresh steps
and IDs with no copied completions, snapshots or execution history.

The old daily checklist toggle is not a new idempotent session API: repeated toggle
requests intentionally reverse that daily state. The unique routine/date constraint
still prevents duplicate rows. Day 24 must introduce desired-state, versioned,
idempotent session-step completion; that requirement is not falsely marked complete
in this stage.

## Security and accessibility

Verified login, live workspace membership and centralized permissions apply to every
new route. Viewer direct writes, foreign routine/step/profile IDs, stale versions,
forged destinations and CSRF failures are tested. Built-in SVG/icon/color identifiers
are allowlisted; no uploads, arbitrary CSS or user HTML are accepted. Jinja escapes
stored text, and the live preview uses text nodes. Audit events contain action types
and IDs, not routine descriptions or step instructions. Existing private-page
headers and session/revocation protections remain in force.

Routine names allow 80 characters, descriptions 1,000, category names 40, step titles
80, step instructions 500 and each routine 1–30 steps. Builder POSTs allow up to
256 KiB before CSRF parsing, enough for the maximum valid Unicode form after URL
encoding. Other account/application forms retain the 64 KiB limit. Oversized requests
receive a branded 413 without saving a partial routine.

Labels, visible focus, semantic headings, polite reorder announcements, explicit
keyboard controls, native disclosure elements, 44-pixel controls, reduced-motion
behavior and responsive layouts were checked. Dragging is never the only way to
reorder; the pointer-only drag handle does not add a dead keyboard tab stop. Optional
step instructions/icons remain available with and without JavaScript. No formal
WCAG conformance certification or independent security audit is claimed.

## Testing and repeatable fictional demo

```sh
venv/bin/python -m pytest tests -q
venv/bin/python tests/browser/check_routine_builder.py
venv/bin/python tests/browser/check_ui.py
venv/bin/python tests/browser/check_workspaces.py
```

The new backend tests cover metadata/steps, insert/delete/reorder with stable IDs,
optimistic conflicts, simultaneous editors, archive/restore, historical label and
profile preservation, duplication without completion history, source/destination
scope, direct viewer requests, CSRF, malformed arrays, oversized Unicode bodies,
escaping, search, validation, forced rollback and populated 0006 upgrades.
Existing regression tests continue to exercise accounts, password recovery,
workspace isolation, invitations, session revocation and database constraints.

The browser runner uses a disposable fictional database. It demonstrates creating
and previewing three steps, keyboard ordering, pointer dragging, insertion/removal
focus, saving/reloading, a stale second editor, duplication, filtering, archiving,
restoring, unsaved navigation, native no-JavaScript draft actions, actual touch events
through Chromium and reduced motion. Library, builder and sequence pages are checked
at 1440/1280/1024/768/390/320 widths for overflow, labels, active navigation and sampled
text contrast. Screenshots and sanitized reports are saved under `artifacts/day22`.
No real care-recipient data or publicly accessible shared administrator is used.

## Operations and limits

No new dependency, asset service, frontend framework or environment variable is
needed. The existing Flask/Gunicorn entry points and Render compatibility remain.
The new static asset is `static/js/routine-builder.js`; existing CSS and built-in
SVG macros provide the visuals. Serve templates and assets from the same release
as the migrated application.

Before rollout: quiesce writes, make a complete verified backup, rehearse 0006→0007
on a populated copy, compare original table columns/records and completion history,
run reviewed migrations, then restart the matching application. Verify routine
create/edit/reorder/archive/restore, roles and cross-family denial against staging
PostgreSQL. Downgrade refuses automatic destruction; rollback requires a reviewed
backup/application-version recovery plan and a decision about any intervening writes.
Nothing is auto-deployed.

The legacy-only import tool now requires an empty 0007 destination and refuses
rich routine metadata, steps, snapshots or authenticated collaboration data. It
must not silently discard the new fields to produce an apparently successful import.
Original legacy columns remain supported for explicitly reviewed quarantine imports.

Real SMTP delivery is still unconfigured. Live PostgreSQL/Redis integration and the
previously documented cryptography advisories remain production gates. See the
[workspace security review](workspace-security-review.md). No scan result is treated
as proof of application security. History/player/calendar views and scheduling are
not part of this stage. Library pagination is bounded; no performance benchmark
or cross-browser claim beyond the executed Chromium checks is made.

Suggested commit: `Day 22: Build premium interactive routine builder`.

## Final verification

- Full pytest suite: **109 passed, 1 skipped**, plus five subtests passed. The skip
  is the opt-in live PostgreSQL test; PostgreSQL migration SQL compiled offline.
- Builder/migration/persistence subset: 26 passed before the final additional
  profile-history test; the full final suite includes that additional test.
- Three browser runners: **137 reported checks**, including 102 page/viewport
  combinations, with zero reported failures. Desktop library and mobile builder
  screenshots were inspected. Touch dragging used actual Chromium touch events;
  keyboard and no-JavaScript reorder paths also passed.
- `pip check`, `gunicorn --check-config app:app`, and `git diff --check` passed.
- Local writes were quiesced, a private backup saved at
  `database/backups/pre-day22-20261017.db`, and migration 0007 applied. Every
  original column/record in all **13** pre-existing data tables matched the backup.
  SQLite integrity and foreign-key checks passed. No routine/completion was lost.
- Main local app restarted at port 5000. A separate disposable fictional preview
  runs at port 5052, with an ordinarily verified demo login. Its library, saved
  five-step sequence and builder were checked in Chromium. The earlier preview
  was not overwritten, and demo credentials are not stored in the repository.

Stage review gate: stop here before Day 23. Scheduling, recurrence, the calendar,
guided sessions and full session history are intentionally not marked complete.
No commit, push or deployment was performed.

## Changed-file manifest

- `README.MD`
- `docs/database-migration.md`
- `docs/day-22-implementation-plan.md`
- `docs/day-22-routine-builder.md`
- `migrations/versions/0007_routine_builder.py`
- `olumira/__init__.py`
- `olumira/models.py`
- `olumira/routes/routines.py`
- `services/authentication.py`
- `services/dashboard.py`
- `services/data_transfer.py`
- `services/routine_builder.py`
- `services/routines.py`
- `static/css/style.css`
- `static/js/routine-builder.js`
- `templates/base.html`
- `templates/dashboard.html`
- `templates/routines.html`
- `templates/routines/builder.html`
- `templates/routines/sequence.html`
- `templates/routines/step_field.html`
- `templates/workspaces/profile.html`
- `tests/browser/check_routine_builder.py`
- `tests/browser/check_ui.py`
- `tests/browser/check_workspaces.py`
- `tests/test_persistence.py`
- `tests/test_routine_builder.py`
- `tests/test_routine_builder_migration.py`
- `tests/test_ui.py`
