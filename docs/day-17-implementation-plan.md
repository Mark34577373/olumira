# Day 17 implementation plan

Status: historical inspection plan. The subsequent instruction authorized completing all stages; see [the implementation report](days-17-21.md) for the final work and validation.

Baseline verification (October 17, 2026): `python -m unittest discover -s tests -v`
ran 62 tests: 61 passed, one live PostgreSQL test skipped because no disposable
TEST_POSTGRES_URL was configured. `pip check` found no broken requirements.
`flask --app app db current` reported 0003 (head). No browser checks were rerun
for this documentation-only planning step. Dependency compatibility checking is
not a vulnerability scan or a security audit.

## Verified foundation

The application uses a Flask factory, blueprints, SQLAlchemy, Flask-Migrate,
Flask-Login, CSRF protection and rate limiting. Revision 0003 is the local
database head. Account creation, verification, recovery, encrypted email outbox
and revocable sessions exist. Verification and recovery tokens expire and are
single-use; credential generations invalidate old sessions. Production settings
require PostgreSQL, shared Redis, HTTPS and authenticated SMTP.

Real SMTP delivery remains unconfigured locally. Live PostgreSQL/Redis/SMTP
behavior is not established by SQLite and mocked delivery tests. Preserve the
verification gate; use private development email previews for demonstrations.
Set PUBLIC_APP_URL to the actual local origin: the documented default is port
5050, while the user's recent server ran on port 5000. Canonical email links must
match the running server; never infer that origin from an untrusted request Host.

Today, request authorization assigns current_user.owner_id to g.owner_id.
Routine, observation and dashboard services filter by that individual owner.
Communication customization is browser-local and keyed by user, not workspace.
These boundaries must change together rather than adding a switcher alone.

## Schema and migration 0004

- Add family_workspaces with opaque IDs, validated name, creator reference and
  timestamps. Creator is provenance, not the authorization source.
- Add workspace_memberships with opaque ID, workspace/user foreign keys, unique
  workspace/user pair, constrained owner/caregiver/viewer role and active/revoked
  status, joined timestamp and indexes supporting membership checks.
- Add nullable workspace_id foreign keys and indexes to routines and observations.
  Completions remain scoped through their parent routine.
- Backfill one private workspace and owner membership per explicitly linked
  existing User.owner_id, assigning only that user's matching records. Preserve
  IDs, completions and content. Unknown/null owners stay unassigned and inaccessible.
  Never attach legacy records to a newly registered user.
- New registrations create their own initial workspace and membership atomically
  with the account and starter routines. Additional workspaces begin empty.
- Retain legacy ownership columns temporarily for compatibility and provenance;
  runtime authorization uses membership and workspace_id exclusively. No dual
  ownership authorization fallback. Document later removal separately.

Test upgrades from populated 0003, empty databases and unclaimed legacy records;
check foreign keys, unique constraints, record equality and migration/model drift.
Back up the local database before applying a reviewed migration. Do not reset or
deploy databases. Do not offer destructive automatic downgrade behavior.

## Authorization and application changes

Introduce a centralized workspace service that verifies the authenticated,
verified user and reloads active membership from the database on every request.
Session workspace IDs are selection hints only. Invalid or revoked selections
must be cleared without revealing the inaccessible workspace. Explicit selection
POSTs require CSRF and active membership; reject forged IDs.

Create a minimal deny-by-default permission helper now so new shared workspaces
cannot create a temporary write-access gap. Initially only owners can administer
workspaces; caregivers may use existing write workflows; viewers receive read-only
access. Day 20 will expand role-management UI and final-owner protections rather
than retrofitting missing checks. No invitation or membership grant UI in Day 17.

Update every existing route and service to scope reads, counts and writes by the
validated workspace. Resource lookup must combine resource ID and workspace ID.
Return the same missing-resource response for foreign and nonexistent resources.
Reject unauthenticated/unverified access before workspace resolution. Do not cache
role decisions in cookies or allow GET selection to mutate persisted records.

Separate communication browser state by user AND workspace. Do not copy earlier
user-local or legacy shared keys into a workspace. Browser storage is not a shared
collaboration database and cannot be revoked after a user has already downloaded
information; disclose that limitation. Shared persisted communication content is
a separate future change with server authorization requirements.

## Interface

Preserve horizontal navigation, forest/sage colors and existing cards. Add an
accessible workspace selector, explicit active-workspace label and a workspace
list/create flow. Add workspace settings with validated name, creation information,
owner display names, active member count and owner-only rename. Provide onboarding,
empty and permission-denied states. Do not implement deletion. Support keyboard
navigation, visible focus, labeled controls and narrow mobile widths.

## Validation and review gate

Add pytest-compatible tests alongside the existing unittest suite for creation,
atomic rollback, unique membership, authorized and forged switching, revoked
membership, owner-only rename, cross-workspace routine mutations, observation
reads/writes, dashboard metrics, CSRF and legacy quarantine. Verify both allowed
and denied operations. Retain account/session regression coverage.

Run the full suite and migration checks. Exercise create/switch/rename and existing
workflows in Playwright at desktop and mobile sizes, inspect screenshots and check
keyboard behavior. Document exact results and remaining infrastructure limitations.

Expected files include models, migration 0004, the factory request hook, workspace
forms/routes/service, existing data services/routes, registration transaction,
base/workspace templates, communication storage scope, CSS, test fixtures and
workspace/isolation/migration/browser tests, plus README and migration guidance.

After Day 17, report actual modified files, migration, test evidence, limitations
and suggested commit `Day 17: Implement private family workspaces`. Stop for review
before Day 18. Do not commit, push or deploy automatically.
