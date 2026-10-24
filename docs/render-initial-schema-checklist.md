# Initial Render PostgreSQL schema — operator checklist

2026-10-23. **Prepared only: no hosted migrations, role changes or deployment run.**
TLS now connects and SELECT 1 succeeds using verify-full and the explicit Linux
CA file. The missing visible version/auth tables explain the next database failure,
but do not alone prove an empty database. Current repository head: **0022**, one
linear chain of **22 revisions**.

## 1. Freeze writes and confirm the target

- Keep public registration closed and pause application/cron writers during initial
  preparation. REGISTRATION_ENABLED=False alone does not stop other write routes.
- Use the reviewed release checkout in an isolated operator workstation/environment
  with its venv dependencies and PostgreSQL client tools. No Render Shell required.
- Privately confirm the External Database URL, database name and runtime role from
  Render. Permit only the operator's approved current egress IP in the database
  allowlist; remove that access afterward. Do not open access to 0.0.0.0/0.
- Preserve sslmode=verify-full and the exact external hostname. On Render keep
  sslrootcert=/etc/ssl/certs/ca-certificates.crt. **On your Mac/operator machine that
  Linux path may not exist**: use an authentic, readable local CA bundle trusted
  for this endpoint, or an isolated trusted Linux environment with that file.
  Change only the operator URL's root-file path, not TLS verification or hostname.
- Use a real interactive terminal. No set -x, SQL echo, screen recording, URL in a
  command argument, printed environment, source-controlled .env, or pasted secrets.

Run the new **read-only** preflight:

```sh
venv/bin/python scripts/postgres_preflight.py
```

It asks privately for the URL and expected database/role/schema (normally public).
It prints only comparison booleans, static application-table flags, object counts
and server version. Run once with the runtime login, once with the migration/owner
login. No record values, actual role/schema/database names or URL are printed.

Expected decision gates:

| Result | Required action |
| --- | --- |
| database_matches/role_matches false | STOP: wrong target/role or unexpected effective role. Compare privately with Render. |
| active_schema_matches/search_path_contains_expected false | STOP: resolve intended schema/search_path first; do not create a parallel schema by accident. |
| catalog_present true but visible/selectable false | Existing tables may be outside search_path or inaccessible. Review schema USAGE/table grants as owner. Do not run initial migrations blindly. |
| in_expected_schema false but catalog_present true | Existing Olumira tables live elsewhere. Review the correct database/schema and migration history; do not duplicate them. |
| Any non-system relation/sequence/function exists | STOP for owner review and backup: the database is not demonstrably empty. Unrelated extension objects can also cause this result. |
| Both roles see zero user objects, identities match and expected schema is usable | Supports initial-schema preparation in this database. Owner must independently confirm inventory/absence of custom types, extensions or other objects not counted by this helper. |

The helper reads pg_catalog rather than information_schema's privilege-filtered
views. It checks the **connected database only**, not other databases on the same
instance. Its checks cannot prove a live production state until the operator runs
it. Do not publish raw pg_catalog listings. Missing-table reflection alone is not
an emptiness check.

## 2. Recovery gate before any schema/grant changes

Render Free databases have no managed recovery/logical-export service. Use an
independent logical backup even if the intended database appears empty. Paid
backups may supplement, not replace, the reviewed recovery plan.

- Install pg_dump/pg_restore compatible with the server version printed by the
  preflight (pg_dump must support that server major; do not assume PostgreSQL 17).
- Use a backup login able to read all intended objects, not a restricted role that
  silently omits the actual dataset. Preserve a private role/grant/search_path
  inventory separately; the existing helper exports no owner/ACL assignments.
- Store backup output outside Git on approved encrypted storage. Provision and
  retain BACKUP_ENCRYPTION_KEY in the operator vault. Do not print the key.
- Securely supply PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD, PGSSLMODE=verify-full,
  and PGSSLROOTCERT pointing to the operator's authentic CA file, plus the backup
  encryption key, using an approved secret manager/session. Never put their values
  in argv or shell history.

Exact existing backup command, after those private environment prerequisites:

```sh
venv/bin/python scripts/encrypted_backup.py --output /ABSOLUTE/SECURE/PATH/pre-schema.enc
```

Use a **new** path; the helper refuses overwrite, enforces verify-full, suppresses
pg_dump stderr and authenticates an encrypted read-back. It caps the unencrypted
dump at 64 MiB; use an approved streaming backup process for larger datasets.
Authenticated read-back does not prove restorable contents. Verify the backup/key
pair and perform a restore rehearsal into a **separate new empty database** using
[the recovery procedure](database-backup-recovery.md). Never test restore against
this production database. Do not proceed without a recoverable backup and a named
operator accepting the recovery plan. No backup has been taken by this task.

## 3. Establish migration/runtime roles and schema policy

Use distinct logins:

- **Migrator:** CONNECT on the intended database; USAGE and CREATE on the intended
  schema; ownership of all Olumira objects it creates; privileges to ALTER/index
  existing owned objects for future releases. Ordinary fresh migrations need no
  superuser, CREATEDB, CREATEROLE or replication rights. A schema owner can grant
  the schema permissions. Provisioning logins itself needs an authorized role
  administrator; if Render limits this, use its supported administration/support
  path, not a privilege bypass.
- **Runtime:** CONNECT, schema USAGE, product-table SELECT/INSERT/UPDATE/DELETE and
  sequence USAGE/SELECT; SELECT only on alembic_version. No schema CREATE, DDL,
  migration ownership or membership that inherits migrator ownership.

If the current Render URL is a database-owner login, it can be the isolated
migrator, but cannot also be treated as a least-privilege runtime login. Arrange a
separate runtime role before reopening traffic. Do not rotate credentials or
transfer ownership of existing shared objects without a separate review.

Agree on one schema before migration; these migrations use unqualified table
names. For a dedicated new Olumira database, **public** is the simplest existing
layout. Role/database search_path settings must put the same intended schema first
for the runtime and migrator. Do not rely on URL options=search_path: the app's
existing connect_args set statement/lock options and can replace URL options.
Do not add writable/untrusted schemas to search_path.

The following is a **review template**, not automatically executed. Replace quoted
identifier placeholders privately and run through an approved administrative
connection only for this dedicated database. Passwords belong in secure interactive
password-setting tools, never SQL literals or these files.

```sql
GRANT CONNECT ON DATABASE "DATABASE_NAME" TO "MIGRATOR_ROLE", "RUNTIME_ROLE";
GRANT USAGE, CREATE ON SCHEMA public TO "MIGRATOR_ROLE";
GRANT USAGE ON SCHEMA public TO "RUNTIME_ROLE";
-- Dedicated database only: review impact before revoking shared PUBLIC grants.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM "RUNTIME_ROLE";
ALTER ROLE "MIGRATOR_ROLE" IN DATABASE "DATABASE_NAME" SET search_path = public;
ALTER ROLE "RUNTIME_ROLE" IN DATABASE "DATABASE_NAME" SET search_path = public;
```

An owner runtime role can retain effective CREATE/DDL despite these revokes; role
separation is essential. Run the read-only preflight again to confirm expected
identity/schema and schema_create=false for runtime, true for migrator.

## 4. Check compatibility on an isolated disposable target first

The full chain generates PostgreSQL offline SQL through 0022 successfully. Review
found additive CREATE/ALTER and legacy backfills/resource seeds, with no DROP,
TRUNCATE or DELETE upgrade operations and no explicit autocommit/concurrent-index
blocks. **Offline compilation is not a live PostgreSQL migration/grant test.**
There is no local PostgreSQL server installed for a live fresh-PG run in this task.
Before production, use a new disposable PostgreSQL database with matching major
version and schema/role policy; never point integration tests at production.
Existing opt-in tests must receive separate empty disposable targets:

```sh
# URLs must be injected privately by your secret manager, not typed into history.
venv/bin/python -m pytest -q tests/test_postgres.py tests/test_postgres_security.py
```

Required private settings: TEST_POSTGRES_URL and TEST_POSTGRES_SECURITY_URL, each
pointing to its own empty disposable database with verified TLS and correct local
CA path. Those tests migrate and write fictional data. Skips are not passing live
PostgreSQL evidence. Retain disposable targets for inspection; do not auto-drop.

## 5. Run the supported release runner exactly once

Prepare an isolated **operator** process with APP_ENV=production and the existing
valid application startup settings: PUBLIC_APP_URL, SECRET_KEY,
MAIL_ENCRYPTION_KEY, RATELIMIT_STORAGE_URI, MAIL_BACKEND=smtp, MAIL_FROM, SMTP_HOST,
SMTP_USERNAME, SMTP_PASSWORD and appropriate SMTP_SECURITY. Load required secret
values from the approved vault; do not print/export them in a terminal transcript.
The full app factory validates them even though migration sends no mail. Do not
use development/testing to bypass production validation.

Only the isolated operator process receives **MIGRATION_DATABASE_URL** with the
migrator login, exact external hostname, sslmode=verify-full and operator-valid CA
path. Do not put that variable in the Render web/cron environment group. Set
OLUMIRA_DB_DIAGNOSTIC=0 in this operator process; avoid inherited PGHOST/PGSERVICE
or other conflicting identity defaults. Ensure capacity for **two** connections:
release advisory-lock connection plus migration engine connection.

If the other required settings are already loaded privately, this interactive
wrapper prompts for the migration URL without putting it in history or argv:

```sh
venv/bin/python - <<'PY'
import getpass, os, runpy
os.environ['APP_ENV'] = 'production'
os.environ['OLUMIRA_DB_DIAGNOSTIC'] = '0'
os.environ['MIGRATION_DATABASE_URL'] = getpass.getpass('Migration External URL with verified TLS (hidden): ')
runpy.run_path('scripts/migrate_release.py', run_name='__main__')
PY
```

It executes the existing supported command in the same process:

```sh
venv/bin/python scripts/migrate_release.py
```

Expected: nonblocking PostgreSQL advisory lock acquired; upgrade messages through
0022; exit 0. An empty database has no version table initially; Alembic creates it.
There is no need for create_all or stamp. A second runner fails on the lock. Do not
put either command in Gunicorn, build startup or concurrent web workers. Migration
stdout contains revision metadata/static SQL context, not credentials; do not turn
on SQL echo or dump application configuration. Stop on any nonzero exit.

## 6. Grant runtime access after migration, before traffic

As the actual object owner/authorized administrator, apply reviewed grants only to
this dedicated schema. Use one transaction so the temporary broad table grant is
not exposed before the version-table restriction:

```sql
BEGIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "RUNTIME_ROLE";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "RUNTIME_ROLE";
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON public.alembic_version FROM "RUNTIME_ROLE";
GRANT SELECT ON public.alembic_version TO "RUNTIME_ROLE";
ALTER DEFAULT PRIVILEGES FOR ROLE "MIGRATOR_ROLE" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "RUNTIME_ROLE";
ALTER DEFAULT PRIVILEGES FOR ROLE "MIGRATOR_ROLE" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO "RUNTIME_ROLE";
COMMIT;
```

Default privileges apply to future objects created by **that owner role**, not
all roles or existing tables. Review any independent inherited/PUBLIC grants; the
block is not proof of least privilege by itself. Never grant runtime schema-owner
membership merely to fix a denied INSERT or sequence nextval.

## 7. Post-migration acceptance and recovery

1. Run the read-only preflight as runtime: identities/schema match; each known
   relation is present in the intended schema, visible and selectable. Runtime
   schema_create remains false. Use the same runtime login for actual application.
2. Manually restart/redeploy web/cron to clear stale pools. Preserve the working
   verify-full/CA settings. Temporarily run startup diagnostics and require:
   connection=connected; select_1=ok; alembic_version=present;
   migration_revision current/expected both [0022]; every required table's
   columns_present with empty missing_columns. A missing version table after a
   successful runner suggests wrong database/schema/role; STOP rather than stamp.
3. Require /health/ready to return 200/ready (also checks shared Redis). Do not
   expose credentials in curl arguments or publicly log diagnostic internals.
4. During the approved fictional-data test window, enable permitted registration,
   register one fictional account, expect check-email rather than 500, confirm
   actual verification email delivery, verify, log in, complete/skip setup and open
   dashboard. Check duplicate signup remains generic and creates no extra account.
   Verify runtime can perform required writes/sequences and cannot perform DDL.
   Keep normal CSRF, secure cookies, hashing and workspace checks enabled.
5. Disable OLUMIRA_DB_DIAGNOSTIC (0/remove); restore intended beta signup policy,
   remove operator network access and unload migration/backup credentials from the
   operator environment. Record release SHA, backup reference, revision and results
   privately. No hosted authentication or schema acceptance has occurred in this task.

If a migration fails: keep writers paused, preserve logs without SQL values, rerun
read-only inventory/revision checks. PostgreSQL normally provides transactional DDL,
but do not assume all 22 revisions rolled back without checking. The lock runner
releases its advisory lock; failed connections also release session locks. Never
retry concurrently, stamp head, reset, drop or downgrade to make errors disappear.
Review a forward repair or restore the verified backup into a **new** empty
isolated database, validate roles/grants/TLS/schema and auth, then authorize a
controlled URL switch. Preserve the original database and incident evidence.
Reverting application code alone does not reverse schema/data changes.

## Local verification for this preparation

`tests/test_postgres_preflight.py`: identity comparisons, hidden-schema detection,
read-only ordering, redaction/strict URL handling and full 22-revision PostgreSQL
SQL generation. **4 passed**; one existing OpenSSL legacy-provider warning.
No live PostgreSQL, hosted preflight, backup, grants, migration or auth test was
executed. The preflight is new operator tooling; application/auth/runner code is
unchanged. Existing unrelated TLS documentation changes were preserved.

Sources: [Render backup limitations](https://render.com/docs/postgresql-backups),
[PostgreSQL schemas/search_path](https://www.postgresql.org/docs/current/ddl-schemas.html),
[owner-specific default privileges](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html).

## Interactive backup convenience command

After compatible pg_dump tools are installed, the operator may run:

```sh
venv/bin/python scripts/backup_postgres_interactive.py
```

Paste the same working Mac preflight URL into its hidden prompt. The wrapper
retains verify-full and the supplied authentic local CA path, removes conflicting
inherited PG* defaults only in the backup subprocess, and invokes the existing
bounded encrypted-backup helper. It does not migrate or change hosted records.

A new random encryption key is written with mode 0600 under
~/.config/olumira-backup-keys; the encrypted backup is stored under
~/.local/share/olumira-backups. Both directories are private (0700), outside this
repository. File names are random and never overwrite earlier backups/keys.
The command prints file paths, never the URL, password, key contents or dump data.
Move the recovery key into the approved vault separately from backup storage.
Local encrypted read-back still does not replace the separate restore rehearsal.
The wrapper was tested with mocked backup execution; no hosted backup was run
by the assistant. Three wrapper tests passed; no production changes were made.

## Completed local recovery rehearsal

On 2026-10-23 the operator's authenticated encrypted pre-schema backup was restored
successfully using PostgreSQL 18.6 into a newly initialized private local cluster.
Zero non-system tables were restored, consistent with the operator's successful
production catalog preflight reporting no application relations. The rehearsal
used no TCP listener and a private Unix socket, stripped inherited PG* connection
defaults, and never contacted Render. The temporary server was stopped and its
cluster removed. The original encrypted backup and recovery-key file were retained.
This confirms this archive can be restored; it does not establish post-migration
schema/authentication compatibility. No Alembic migration or hosted schema change
was run. Runtime-role separation and the isolated release environment remain
prerequisites before opening production traffic.

New manual helper: scripts/rehearse_postgres_restore.py, accepting backup and key
**file paths**, never key values or database URLs. Two mocked isolation/privacy
regressions passed in addition to the actual local restore rehearsal.

## Optional manual interactive migration preparation

The verified-backup operator may run
`venv/bin/python scripts/migrate_release_interactive.py` in an interactive terminal.
It privately asks for the Mac-compatible migration URL, expected identity and
existing production configuration values from Render. It first repeats the
read-only catalog preflight and refuses nonempty targets or identity/schema/CREATE
mismatches, then validates production startup configuration without initializing
the web app or sending SMTP. Nothing is written to credential files.

It prints the reviewed head 0022 and waits for the exact `MIGRATE 0022` confirmation.
Pressing Enter cancels; no migrations run before confirmation. Only a deliberate
operator confirmation calls the existing scripts/migrate_release.py with secrets
in its private subprocess environment, never command arguments. Do not confirm
until writers are paused, the target/role is approved and backup/recovery gates
have passed. It does not provision runtime roles or automatically grant privileges.
The operator still must verify runtime grants, hosted schema and auth afterward.
The assistant did not execute this wizard against production.
