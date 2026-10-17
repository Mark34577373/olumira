# Database migration and recovery runbook

## Current schema and compatibility

The initial Alembic revision is `0001`; the current head is `0003` (users, revocable sessions, account recovery, and encrypted email queue). See the [Day 16 runbook](day-16-account-recovery.md) before enabling account/recovery flows. Baseline 0001 represents the original tables below; later revisions add account functionality without rewriting those records:

| Table | Columns and relationships |
| --- | --- |
| owners | Text id primary key, required text created_at |
| routines | Integer id primary key, nullable text owner_id, required text name/category; owner index |
| observations | Integer id primary key, nullable text owner_id, required text activity/date, nullable notes/mood/tags; owner index |
| routine_completions | Composite primary key (routine_id, completion_date); routine_id references routines.id with ON DELETE CASCADE |

Dates remain ISO text to preserve historical values. No new timestamps or account entities are invented. Existing workspace boundaries are preserved. Nullable owner fields remain nullable for older unowned records; import never silently assigns them to a visitor. Owner foreign keys are deferred until legacy ownership can be resolved through an explicitly approved future migration. Repeated routine names are legitimate; primary-key duplicates are rejected rather than deduplicating records by content.

SQLAlchemy now handles application persistence. Flask-Migrate/Alembic handles schema evolution. `create_all()` is not used. Startup never migrates tables or deletes old workspaces. Database errors roll back and display branded, generic error feedback. Scoped sessions are removed on context teardown. Import uses one transaction, locks destination tables on PostgreSQL (or takes a SQLite write lock), and rolls back on insert or verification failure.

## 1. Back up and inspect the source

Arrange a maintenance window before a real cutover: stop writes so no changes arrive after the backup snapshot. Keep the old deployment and its database available for recovery. Store backups in restricted, ignored local storage; never upload private records to Git.

The SQLite online backup API creates a consistent snapshot; the commands require a new backup filename and will not overwrite one:

```sh
venv/bin/python -m flask --app app backup-sqlite \
  --source database/olumira.db \
  --backup database/backups/reviewed-source.db
```

The command validates integrity, columns, required values, primary keys, calendar dates, owner relationships, and completion relationships, and prints only table counts. Unknown ownership, malformed dates, missing fields, or an unsupported schema stop the process. Resolve issues in a separate reviewed copy; never delete records just to make validation pass. Backups have owner-only file permissions.

A local backup was already created for this task at `database/backups/pre-day13-20261016.db`: 3 owners, 15 routines, 0 observations, 3 completions. The original database was not stamped, upgraded, or transferred. Use a fresh filename for later backups.

## 2A. Continue using an existing local SQLite database

The original tables already exist, so running the baseline upgrade directly would try to recreate them. Instead, explicitly adopt the schema after backup and validation:

```sh
venv/bin/python -m flask --app app adopt-legacy-sqlite \
  --backup database/backups/before-baseline-adoption.db
venv/bin/python -m flask --app app db current
venv/bin/python -m flask --app app db upgrade
```

Adoption requires exactly the four supported tables, column types/nullability, primary keys, expected indexes, and the cascading completion foreign key. It snapshots and validates data, then stamps baseline 0001. It changes only Alembic bookkeeping, never application records. Refusal means manual review is needed; do not bypass it with a blind `flask db stamp`.

## 2B. Prepare an empty destination

For a new local SQLite database, create its parent directory and set `DATABASE_URL` to an absolute SQLAlchemy SQLite URL (`sqlite:////absolute/path/to/destination.db`). For PostgreSQL, set the reviewed destination's URL in your shell or hosting environment; do not paste credentials into source files or terminal transcripts.

Then run:

```sh
venv/bin/python -m flask --app app db upgrade
venv/bin/python -m flask --app app db current
```

The expected destination revision is 0003. Run upgrade again to confirm it is a no-op. PostgreSQL is configured through psycopg with connection pre-ping. Use the provider's required TLS parameters; app settings never turn TLS verification off. Do not expose connection strings in screenshots/logs.

## 3. Transfer into the empty, migrated target

With `DATABASE_URL` pointing at the intended empty target (including empty user/session/token/email-outbox tables):

```sh
venv/bin/python -m flask --app app transfer-sqlite \
  --source database/olumira.db \
  --backup database/backups/cutover-source.db
```

The command first snapshots the source and imports from that snapshot. It refuses any nonempty application/account/session/token/mail table or an unexpected migration revision. It also refuses source databases containing users, sessions, account tokens, or queued emails: this legacy-only importer must never silently omit account data. All source IDs, nullable metadata, ownership, and completion dates are preserved. It compares every destination row and each table's count before commit, then resets PostgreSQL integer sequences so subsequent inserts cannot collide with imported IDs. The original SQLite database is never removed or overwritten. Verification failures roll back the complete destination import.

The transfer command itself is designed for either an isolated local destination or an explicitly approved production cutover. **Do not run it against a hosted destination until the destination, maintenance window, and cutover are approved.** No production transfer has been performed here.

## 4. Verify before switching traffic

- Confirm migration revision and all four counts against the backup.
- Exercise existing routine completion in the same signed-cookie workspace, then reload and check both routine views.
- Add a disposable routine and observation to verify serial sequences and persistence.
- Check date boundaries using APP_TIMEZONE.
- Verify that a second visitor cannot modify the first visitor's items.
- Verify that the stable signing key remains unchanged if existing cookie workspaces must stay accessible.
- Check generic error pages and sanitized server logs; do not put private data in logs.
- Keep source and backups until retention and recovery have been reviewed.

## 5. Recovery

If validation or import fails, the target transaction rolls back; the source and backup remain intact. Inspect the target locally before any retry. A partially applied **schema migration** is a separate condition: inspect Alembic state and restore an empty reviewed destination rather than assuming DDL was fully transactional on SQLite.

If cutover validation fails before accepting new writes, keep or restore traffic to the old deployment with its original database and stable signing key. If new writes have been accepted on PostgreSQL, stop writes and reconcile them through a reviewed recovery plan before reverting, to avoid losing post-cutover records.

Restore SQLite only while the app is stopped, to a **new path**, verify it, then point the app at that path. Do not overwrite the original or the only recovery snapshot. Baseline downgrade deliberately refuses to drop tables. Production rollback, table deletion, and restoring over an existing database require explicit approval and are not automated by this project.

## What was actually tested

Automated tests exercise baseline creation/repeated upgrade, model agreement, legacy adoption, constraints, cascade deletion, rollback, workspace isolation, and SQLite-to-SQLite import with exact row verification, refusal of nonempty targets, and forced mid-import failure. The PostgreSQL baseline was also compiled to SQL offline (without a server). No live PostgreSQL server was available. An opt-in `TEST_POSTGRES_URL` test covers PostgreSQL migration, transfer, completion preservation, and sequence advancement against a new disposable database. It remains skipped until that environment is supplied.

Implementation follows the official [Flask application factory pattern](https://flask.palletsprojects.com/en/stable/patterns/appfactories/), [Flask-SQLAlchemy configuration](https://flask-sqlalchemy.palletsprojects.com/en/stable/config/), and [Flask-Migrate migration commands](https://flask-migrate.readthedocs.io/en/latest/).

## Family workspace upgrade: 0003 → 0006

The current head is **0006**. Follow the newer
[family workspace runbook](days-17-21.md#safe-migrations-and-legacy-records) when
upgrading account-era data. Back up the complete database, including account/token/
mail tables, quiesce SQLite writes, then apply `flask --app app db upgrade` before
starting the new app. Verify all original columns/records plus completion history
against the backup. Migrations add scope without recreating routine parent tables.

0004 backfills workspaces only for explicit existing User.owner_id associations;
unknown/null legacy owners remain unassigned. 0005 adds optional profiles and leaves
existing content at workspace level. 0006 adds invitations, encrypted outbox linkage
and append-only audit events. No automatic deletion or downgrade is supported.
A failed partial SQLite DDL upgrade requires reviewed backup recovery.

The legacy-only transfer command now requires an empty **0006** destination and
refuses source/destination account, workspace, profile, membership, invitation or
audit data. It does not transfer authenticated collaboration databases. Earlier
0003 instructions in this document describe the historical account release; use
this section and the linked runbook for the current application.

## Routine builder upgrade: 0006 → 0007

The current application head is **0007**. Back up all tables, quiesce writes and
apply the reviewed additive migration before starting this release. Existing
routine IDs, ownership/profile scope, names and completion dates are preserved;
no routine parent-table rebuild or automatic deletion occurs. Existing items become
one-step templates. Completion label/scope snapshots are marked as adoption-time
captures; no historical step sessions or original creators are invented.

Read the [Day 22 migration/report](day-22-routine-builder.md). Verify every original
column/record and foreign keys against the backup. Destructive automatic downgrade
is refused. Restore a reviewed backup with the matching code if recovery is needed.

Legacy-only transfer now requires an empty 0007 destination and refuses rich routine
metadata, steps and snapshots in addition to account/workspace data. Use a complete,
reviewed database migration for the authenticated application; do not use that helper
as an exporter of a modern collaboration database.


## Days 23–24 additive scheduling and guided-session tables

Current head is `0009`. Migration `0008` adds schedule revisions and materialized
occurrence identities; `0009` adds frozen guided runs/steps, caregiver activity,
and idempotent launch requests. Neither rewrites parent routines or legacy daily
completion dates. Back up before upgrading, verify preserved rows and foreign keys,
and restart with matching application code. The legacy-only transfer refuses these
records rather than discarding them. Downgrade requires an explicitly reviewed
backup restore. See [the Days 23–24 runbook](day-23-24-routines.md).


## Days 25–26 communication tables

Current head is `0011`. Migration `0010` adds private communication boards/cards;
`0011` adds explicitly saved profile/workspace phrases. Both are additive and leave
all existing rows/columns unchanged. Browser-only choices are preserved separately
at `/communication/quick`; no automatic publication/import into shared data occurs.
Back up, migrate and restart with matching code. The legacy-only transfer refuses
communication tables. Downgrades refuse deletion; use a reviewed backup restore.
See [the communication runbook](day-25-26-communication.md).


## Days 27–28 personalization and caregiver workflows

Current head is `0013`. `0012` adds profile preferences and favorite references;
`0013` adds tasks, immutable handoffs, recipient acknowledgments and task links.
Both are additive with scope/history guards and preserve all previous rows/columns.
Stop writers and verify a complete backup before upgrading; restart matching code.
The legacy-only transfer refuses these new records. Downgrades refuse data deletion;
rollback requires a reviewed backup/code/key restore. See [the runbook](day-27-28.md).

## Days 29–32 additive journal extension (0014)

Head 0014 adds journal metadata and scope/time/category/completion indexes without rebuilding legacy tables. Existing authors/event/creation times remain unknown when not recorded. Observation author, creation and scope are preserved; linked sessions/tasks must match scope. No reporting tables or public file storage are added. Back up, migrate, restart, and follow [the Days 29–32 runbook](day-29-32.md). Legacy-only transfer refuses rich observation metadata rather than silently discarding it.
