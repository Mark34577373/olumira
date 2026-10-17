# Days 22–24: inspection and Day 22 implementation plan

Status: historical inspection/design plan; Day 22 was subsequently implemented.
See [the completion report](day-22-routine-builder.md) for actual behavior and evidence. The new master prompt requests a plan first, then three
implementation stages with review after each stage. Nothing will be committed,
pushed or deployed automatically.

## What the repository actually contains

The working tree was clean before this plan. Local migration head is 0006.
The Flask factory, SQLAlchemy, workspace memberships, care profiles, centralized
roles, verified accounts, invitation outbox and append-only audit events exist.
Real inbox delivery remains unconfigured; private development previews work.
Live PostgreSQL/Redis operation and the previously documented dependency findings
remain deployment gates, not completed hosted verification.

Current routine behavior:

- `Routine` stores an integer ID, legacy owner key, nullable workspace/profile,
  name and category. It has no steps, template version, archive state or scheduling.
- `RoutineCompletion` records a unique routine/date pair. It is not a session or
  a step history. Deleting the parent currently cascades away those completions.
- `services/routines.py` scopes HTTP queries through the resolved workspace and
  selected profile. It offers basic add/edit/delete, category templates and a
  daily toggle. The toggle is not idempotent: repeating it reverses the result.
- The factory checks create/edit/complete permissions and locks the workspace
  before existing routine mutations. New endpoints must be added explicitly;
  relying on the old endpoint mapping alone would leave a permission gap.
- The dashboard derives actual daily completion counts from the same scoped
  checklist. Its observation summary currently loads every observation in scope;
  that query should be bounded when upcoming routines/history are introduced.
- Existing templates provide a checklist and basic forms, without a builder,
  search, archive library, drag controls, calendar or player.

The pre-change baseline ran 92 tests: 91 passed, one live PostgreSQL test skipped,
and five additional subtests passed. The local database was at 0006.
No browser or accessibility checks have been rerun for this documentation-only step.

## Day 22 schema and preservation strategy

Create reviewed migration **0007** using additive changes:

1. Keep `Routine.id`, `name`, category and scope. Extend the model with bounded
   description, allowlisted icon/color, archive timestamp, editor version,
   creator reference and creation/update metadata. Keep historically unknown
   creator/timestamps explicitly unknown rather than inventing original authorship.
2. Add `RoutineStep`: opaque ID, routine foreign key, title, optional description,
   icon, sort position and timestamps. Enforce unique positions per routine and
   valid references. Server validation limits routines to 1–30 steps, with bounded
   fields and a complete, duplicate-free ordering payload.
3. Convert each old checklist item into one routine with one step using its current
   label. Do not merge items by category, infer medical meaning, transfer unknown
   ownership or change existing IDs/completion dates. Legacy quarantined records
   remain quarantined.
4. Preserve the original completion table. Where an adoption-time label snapshot
   is needed, label it as captured during migration: historical step details and
   the original label at completion cannot be reconstructed from the old schema.
   Do not fabricate step sessions or caregiver attribution for legacy completions.
5. Replace public hard deletion, including the existing delete URL, with archiving
   so old clients cannot erase completion history. Restore is an explicit action.
   Update regression expectations for this intentional behavior change; retain
   separate foreign-key/cascade constraint tests using disposable fixtures.

Avoid rebuilding the SQLite routine parent table with foreign keys enabled: that
can cascade-delete completion records. Prefer additive columns/new tables; if a
rebuild proves necessary, rehearse a preservation-safe sequence against a populated
copy before touching the local database. Freeze migration definitions independently
of live model imports. Test SQLite upgrade, PostgreSQL offline SQL, model drift,
foreign keys, original row equality, legacy quarantine and repeated upgrade.

Back up the actual local database and quiesce writes before applying the tested
migration. Never reset it. Refuse destructive automatic downgrade; document a
reviewed backup/application-version recovery procedure. The fictional preview on
port 5051 uses a disposable database and must be refreshed separately after changes.

## Day 22 service and authorization design

- Add routine-builder validation/forms and a dedicated service for reading/saving
  the entire ordered routine transactionally. Preserve useful checklist helpers
  while making the authorized workspace/profile boundary explicit in new APIs.
- Lock in the existing workspace-first order, reload current membership, check the
  exact capability, and locate the routine through its current authorized scope.
  Apply the same checks to every submitted step ID and destination profile.
- Permit profile reassignment only within the active authorized workspace, after
  validating the destination against database profiles. Later sessions retain their
  own immutable original workspace/profile association; history authorization must
  not depend on a template's subsequently changed profile.
- Use a monotonically increasing template version for edit/archive/restore/reorder
  operations. A stale editor receives a 409 conflict and keeps its submitted work
  available for review instead of silently overwriting another caregiver's edits.
- Replace the ordered step collection atomically; distinguish valid existing IDs,
  new steps and deletions. Use a collision-safe two-phase ordering update so swaps
  cannot violate unique positions partway through a save. Roll back on failure.
- Duplication copies metadata and ordered steps into an authorized destination;
  generate fresh IDs and copy no completion/session/schedule history.
- Archive/restore preserves all history. Archived templates are read-only until
  restored and excluded from active library/dashboard/schedule queries. Do not
  leave old toggle/edit/template endpoints as authorization or archive bypasses.
- Add minimal audit events containing IDs and action types, never titles,
  descriptions, care notes or raw submitted JSON.
- Keep viewer access read-only, including direct requests. Use normal HTML forms
  with CSRF and progressive enhancement; JSON/fetch requests, if used, must receive
  the same validation and CSRF enforcement. No new frontend framework is needed.

The existing daily toggle remains legacy behavior until replaced by Day 24's
explicit completion/session operations. It must not be presented as an idempotent
session-completion API or create invented historical step progress.

## Day 22 interface

Preserve the forest/sage palette, nature illustrations and horizontal navigation.
Build a routine library with visual cards, search, category and active/archive
filters, scoped profile selection, pagination and thoughtful empty states. Keep
secondary duplicate/archive/restore actions in a compact accessible disclosure.

The builder has labeled sections for identity, description, profile, category,
allowlisted built-in icon/color choices and ordered step cards. A live preview uses
text nodes/escaped content, not user HTML. Optional templates copy a complete
editable sequence into the current workspace/profile; they are never shared editable
global records. Saving and cancellation have clear feedback and unsaved-change
protection that is cleared after a confirmed save.

Provide visible drag handles with pointer/touch support scoped to the handle so
ordinary page scrolling still works. Always provide native Move up/Move down
buttons and a polite ordering announcement. Preserve focus on the moved item and
give predictable focus after deletion. Reordering is persisted only through the
validated save transaction. Avoid animation when reduced motion is requested.
Native form submission and explicit reorder controls must remain usable without
dragging. Do not add a dependency unless native controls prove inadequate.

Routine sequence preview is distinct from a persisted guided session. Day 24 adds
the real launch/resume workflow; do not show a nonfunctional Start control or claim
guided execution is delivered at Day 22.

## Later-stage contracts to preserve now

### Day 23: scheduling

Add schedules with IANA timezone, local wall time, one-time/daily/weekly/selected
weekday recurrence, effective start/end dates, active/paused/ended state and a
schedule revision. Generate only bounded requested windows (daily/seven-day views,
short upcoming list), not an unbounded recurrence table. Materialize an occurrence
only when needed for an execution, with a unique stable identity containing schedule
ID, schedule revision and local occurrence date. A refresh or retry must not create
another occurrence. Concurrent materialization uses a unique constraint.

An edit creates a new effective schedule revision and changes only future unstarted
occurrences. Persisted/in-progress/completed occurrences retain their original UTC
time, local date, timezone and revision. Overlaps are allowed but shown; exact
duplicate schedules are rejected under a lock. Reject invalid ranges and one-time
dates already past unless an explicit historical-entry workflow is added later.

Document DST policy: choose the first fold for an ambiguous local time; skip a
nonexistent local time and explain the skipped occurrence in the schedule preview.
Never silently shift a time into another hour. Verify round-trip conversion through
UTC with ZoneInfo and test both transitions. Display the schedule timezone explicitly;
workspace/user timezone preferences may later control display, never server-local
time. Archive suppresses future occurrences without rewriting historical executions.

### Day 24: guided sessions

Introduce session and session-step snapshots, frozen at launch, including routine
title, profile association, step labels/order/icons and template revision. Edits or
archives cannot rewrite a completed session. Preserve legacy completion dates as
legacy records rather than pretending that step history existed.

Use a unique occurrence/session association and a transactionally enforced single
active ad-hoc session per routine/profile. Retries resume that session; a new run
after completion requires an explicit new-run intent/idempotency key. Session
actions include a state version and desired step state, not a toggle. Completed
session-step undo is available only while the session remains unfinished; finished
history is immutable. Pause/resume, step changes and completion use the same lock
order and reject conflicting stale updates with understandable refresh feedback.

Guided and overview views share database state. Navigation changes the displayed
step without claiming it was completed. Progress comes from actual snapshot step
states. Dashboard counts must clearly distinguish completed routine runs from
completed steps and preserve the legacy checklist definition during transition.
History has bounded pagination and profile/routine/date/status filters. No WebSocket
dependency is needed: show revision/conflict feedback and an explicit refresh path.

## Validation and stage report

Day 22 backend tests will cover create/edit, step insertion/removal/reorder, stale
versions, duplicate/missing/foreign step IDs, duplication without history, archive/
restore, old endpoint behavior, profile reassignment, authorization, direct viewer
writes, CSRF, validation, escaping, rollback and populated legacy migration.

Run existing account, workspace, dashboard, observation and communication regressions.
Use Playwright for the full create/add/edit/reorder/save/reload/duplicate/archive/
restore flow, including pointer ordering, touch-friendly controls, keyboard-only
ordering, preview, unsaved changes, error/conflict states and no-JavaScript behavior.
Check 1440/1280/1024/768/390/320 widths, labels, focus, contrast, overflow and reduced
motion. Inspect screenshots. Do not claim formal accessibility compliance or live
PostgreSQL verification without the corresponding evidence.

Expected changes: routine models and migration 0007; routine forms/validation,
routes and service; authorization endpoint mapping; library/builder/sequence
templates; dashboard filters; dedicated routines JS/CSS; migration/authorization/
builder/browser tests; legacy import compatibility; README and implementation/
deployment documentation. Keep saved preview data and real local data separate.

At the Day 22 review gate, report actual implemented features, exact modified files,
migration, executed tests/results, security/accessibility evidence and limitations.
Suggested commit: `Day 22: Build premium interactive routine builder`.
Stop for review before Day 23 as requested in the current master prompt.
