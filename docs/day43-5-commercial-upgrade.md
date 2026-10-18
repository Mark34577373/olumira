# Day 43.5 — commercial care experience

Status: implemented and verified locally. All final executed checks pass. Test data is fictional; no hosted deployment claim.
No commit, push, deployment, external service or real-data approval.

## Unified care plans

`/care-plans` organizes each authorized care profile's existing routines, boards,
responsibilities and observations. The guided editor selects profile context,
priorities, connections, optional first goal and review/status; sections are optional.
Save Draft persists a titled plan. Editing later adds/removes connections atomically,
with version checks. Goals have category, description, optional target date and
planned/in-progress/completed/paused states. The overview reads actual checklist
marks, guided-run completions, upcoming calendar items, assigned tasks and recent
profile observations. Guided-run daily counts are explicitly UTC; checklist dates
use the existing application timezone. No invented score or medical recommendation.

Care Plans is a secondary care-team view and a compact toolbar/dashboard/profile
shortcut; the horizontal primary header remains intact. Routine Studio, tasks,
communication and observations retain their original workflows and records. Select
the desired profile in the existing toolbar before creating/opening its plan. A plan
cannot move to another profile. When returning from creating a connected item in a
new tab, save a draft first and reload choices; cross-tab auto-refresh is not promised.

## Intelligent handoffs

`/care/handoffs/studio` creates deterministic suggestions for a bounded seven-day
maximum shift. Completed runs are filtered by actual completion time; scheduled
unfinished routines use existing recurrence/occurrence state. Current open tasks
are explicitly labeled as current and may predate the shift; this is not a historical
as-of snapshot. Upcoming items cover the next 24h. Each section shows up to five
items, with bounded text, to fit the existing 2,000-character shared-summary contract.
If too much content is selected, the generator asks for fewer sections instead of
silently dropping the final shared text. Full history stays in the original tools.

Observations are never selected by default. Both the observations category and each
item must be selected; it must belong to this workspace/profile, remain active and
have a known timestamp inside the shift. The generator includes only that selected
item's bounded title/notes. No external AI or sensitive-data vendor integration.

Review the editable plain-text sections, remove items/add notes, choose recipient,
save privately, then mark Ready. A separate saved-preview confirmation shares it.
Unsaved new edits disable the Share control until saved. Draft → Ready → Shared
uses author-private `handoff_drafts`; sharing creates the existing immutable
`caregiver_handoffs` and recipient records. Acknowledged is derived from existing
recipient timestamps, not a conflicting second state machine. Retrying a share
returns the same immutable handoff. Acknowledged/shared text cannot be rewritten.
Legacy manual handoffs remain compatible at their original route. History filters
and acknowledgment continue using existing services. No automatic SMTP sharing.

## Advanced Visual Routine Studio

The existing builder now includes step duplication, one-change undo for structural
edits/reordering, richer visual preview cards, optional 0–3,600-second timers and
local preview completion controls. Existing pointer/touch drag, keyboard Move
controls, focus announcements, stable IDs, transactional ordering and optimistic
versions remain. Duplication clears IDs; reorder preserves them. Existing forms
without timer arrays remain accepted, defaulting timers off. Active/new guided runs
freeze timer settings alongside titles/icons/instructions; later builder edits do
not alter running or historical sessions.

Timers use an elapsed wall-clock deadline, pause/resume/reset, and announce completion
once. They are optional local browser guides, reset on navigation, and never call
completion APIs or penalize anyone. Preview state is likewise local, creates no
sessions/completion history, and resets when the draft changes. No animations were
added. No custom image upload is added because durable upload infrastructure is not
available. Existing symbol icons remain usable with text and without color.

The fictional template library includes morning, bedtime, school, after-school,
organization, household and communication examples plus prior templates. Opening a
template previews editable steps; Save creates a scoped private routine, never a
public family template. Existing schedules/player/history/analytics stay in place.
`/routines/<id>/print` requires normal profile/workspace authorization and produces a
clean ordered icon/text schedule through print CSS, without navigation or private
workspace metadata. No new PDF dependency; browser print can save a PDF.

## Schema and architecture

Additive Alembic **0022**, parent0021: six tables (`care_plans`, `care_goals`,
`care_plan_routines`, `care_plan_boards`, `care_plan_tasks`, `handoff_drafts`) and
`timer_seconds` on routine steps/frozen session steps, default0. The resulting49-table
schema retains historical routines, observations, handoffs and access records.
Foreign keys, indexed scope/author lookup, unique link primary keys and status
constraints apply; no data reset/backfill of personal content. Downgrade refuses
until retained records are reviewed. Legacy transfer's empty-destination checks,
locks and supported head were extended to include the new tables/revision.

Significant implementation files:

- `services/care_plans.py`: scoped references/goals, versioned atomic plan writes.
- `services/handoff_drafts.py`: deterministic filtering, private drafts, explicit
  versioned share through existing care coordination.
- `olumira/routes/care.py`: plan/goals/studio endpoints inside existing protected care blueprint.
- `services/routine_builder.py`, `routine_sessions.py`: optional timers and frozen
  snapshots; existing scheduling/completion logic preserved.
- `templates/care/`, `templates/routines/`, `static/js/`: wizard, review, preview,
  timer and print interactions; existing CSS surfaces with responsive refinements.
- `services/privacy.py`: owner workspace exports include plans/goals/link tables;
  personal exports include only the author's drafts in currently active, open
  workspaces. Workspace exports exclude private drafts. Account closure removes
  personal drafts with other personal records; immutable shared handoffs remain.

## Security, privacy and retention

All HTTP operations use existing verified authentication, live membership, exact
profile scope, role/capability and global CSRF. Server-side checks validate every
linked record and recipient. Drafts require their author, including direct URLs;
shared records retain existing authorized workspace/profile policy. Workspace locks
serialize mutations; versions reject stale forms. Bounded arrays/text/counts keep
requests manageable. Jinja escaping and textContent render user text as text, never
generated HTML. No private text is added to logs, query strings or third-party calls.

Plan/shared history follows existing retained-history access-closure policy, not a
claim of physical erasure. Owner exports include plan data; revoked members cannot
export care drafts from revoked workspaces. Personal account closure deletes its
drafts; already-shared copies/acknowledgments remain as shared history. Restore
procedures must still reconcile closures/revocations and revoke restored artifacts.
Final family-history/backup retention policy and qualified privacy review remain
pending. These additions expand the sensitive-data inventory; they do not approve
real sensitive-data storage or establish compliance.

## Verification and fixes

Focused new features:8passed in23.88s. Existing builder/schedule/plan/handoff batch:
42passed and13subtests in111.95s. A subsequent feature/privacy batch passed17tests in61.62s; persistence/privacy passed17tests in45.99s. Final results follow below. Initial failures were retained and corrected: fixture
profile selection before workspace context, premature plan autoflush before required
fields, preview timer change-event rebuild, tall sticky preview covering Save, and
a stale legacy-transfer schema guard and personal-draft ownership handling during account closure. The old standalone builder browser test now
checks one active link per navigation landmark (primary and secondary navigation
already coexisted) rather than incorrectly requiring only one across the whole page.

Browser evidence: `artifacts/day43-5/result.json` records the complete fictional
plan → template → reorder/timer/preview → save/link → guided completion → observation
→ generated/edited/reviewed handoff → recipient acknowledgment journey. It asserts
outsider denial and author-only draft access, no preview completion writes and
30 page/viewport checks across1440/1280/1024/768/390/320. A print PDF and six plan
screenshots were generated; mobile care-plan screenshot was visually inspected.
No JavaScript runtime errors. Timer start/pause/resume/reset was also verified with simulated wall-clock advancement; paused time remained unchanged. This is representative accessibility evidence,
not formal WCAG certification or a full screen-reader audit.

Existing guided-routine, personalized-care and journal/report browser scripts pass;
standalone builder regression passes pointer, keyboard, mobile touch, stale-save,
unsaved-navigation, responsive labels/contrast and reduced-motion checks. Exact
final commands/counts follow below. No live production or external
SMTP/Redis/Render test is claimed.

## Remaining limits and Day 44

The tested local workflows are ready for controlled fictional-data beta preparation.
Hosted beta still needs Day43's approved resources, TLS/runtime/Redis/SMTP verification,
offsite backup/restore and alert ownership. Local timers are deliberately not shared
across devices or persisted after navigation. The studio does not upload images or
publish private routines as public templates. Handoff suggestions are bounded
explainable current-record summaries, not clinical advice or historical reconstructions.
**REAL-DATA READINESS PENDING.**

## Final executed evidence

- Initial full run:6failed/221passed/29subtests,564.77s. The failures were three
  legacy-transfer checks pinned to0021 and three closure paths assuming every
  personal table used user_id. Both root causes were fixed, not skipped. Initial
  JUnit remains `artifacts/day43-5/pytest-initial-failed.xml`.
- Corrected full PostgreSQL-backed run: **228passed,29subtests**,553.16s;
  **0failures,0skips**. A later-added populated0021 migration case separately
  passed in2.42s. Final affected care/plan/draft/migration batch: **15passed**
  in50.84s, with refreshed coverage after minor validation/UI refinements.
- Final branch-aware security coverage **90.52%**, target85; core **87.60%**,
  target80. The security group now includes both new services. Coverage JSON/XML
  copied into `artifacts/day43-5/`; the existing global config still writes its
  primary outputs under day41-42.
- PostgreSQL17.11 focused preflight:2passed in10.33s. Full final runner also
  exercised both live PG cases, the isolated migration runner producing0022,
  Fernet-authenticated encryption/decryption and pg_restore into a new database.
  Compared source/restored values: revision0022,1board,2users,1care plan,
  1handoff draft and90total optional routine-step timer seconds. The extended
  PG workflow creates/links a routine and goal, saves/shares a reviewed draft,
  acknowledges as its recipient and denies another caregiver the private draft.
  Both private PG clusters stopped; no network TLS/provider recovery is claimed.
- Commercial browser journey passed with no JS errors and30viewport/page checks.
  Existing standalone builder, guided-routine, personalized-care and journal/report
  browser journeys also passed. Builder's old navigation assertion was corrected
  to validate each landmark, retaining primary/secondary active-link checks.
  The new commercial journey is wired into the existing CI browser runner;
  remote CI itself has not run here.
- Print PDF:1page, expected routine text present, workspace/profile toolbar text
  absent. Print CSS hides navigation/actions; no metadata/completion writes.
- Bandit medium/high gate passed,0medium/high results. Literal loopback probe URLs,
  random mode0700 mkdtemp and fixed ORM metadata SQL have narrow reviewed heuristic
  annotations; no request-supplied URL/path/identifier is suppressed. The gate
  remains enabled. Secret-pattern scan:298working files,543reachable history blobs,
  0high-confidence matches; not a complete credential audit.
- Black check on9new/refined modules,4JS syntax checks via Playwright's bundled
  Node, compileall and git diff --check passed. No dependency was installed/changed.

Reproducible executed commands (private PG binary directory is machine-specific):

```sh
venv/bin/python scripts/run_postgres_quality.py --bin-dir /var/folders/mg/tr1k7vxn26302_t9hywpb9m80000gn/T/olumira-postgres-qa-bybcubo7/install/bin --full --artifact-dir artifacts/day43-5
venv/bin/python -m pytest -q tests/test_care_coordination.py tests/test_care_plans.py tests/test_handoff_drafts.py tests/test_commercial_migration.py --cov --cov-append --cov-report=json --cov-report=xml --junitxml=artifacts/day43-5/final-focused.xml
venv/bin/python scripts/check_coverage.py
venv/bin/python tests/browser/check_commercial_care.py
venv/bin/python tests/browser/check_routine_builder.py
venv/bin/python scripts/run_browser_quality.py --only check_guided_routines check_personalized_care check_journal_reports
venv/bin/python -m bandit -r olumira services scripts -ll -f json -o artifacts/day43-5/bandit.json
venv/bin/python scripts/scan_secrets.py --history --output artifacts/day43-5/secrets.json
git diff --check
```

## Local development preview

The existing127.0.0.1:5000 development process was stopped for an additive local
SQLite upgrade, then restarted with development-only local settings. A mode0600
backup was saved in ignored `database/backups/` before migration. Row counts of
all43existing tables were unchanged,6tables were added, revision0022 and
PRAGMA foreign_key_check passed. `local-migration.json` records the private backup
path; no records were reset or seeded. No hosted/production database was touched.

[Open localhost](http://127.0.0.1:5000). Live/ready/login returned200; an
unauthenticated care-plan request redirected302 to login. Existing verification,
login and workspace permissions still apply. Development SMTP remains a private
preview backend; no real email-delivery or verification-transport claim.

Suggested unexecuted commits: care plans, handoff drafts, routine studio, and
commercial integration tests as listed in the master brief. No commit/push/deploy.
