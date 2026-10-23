# Render shared authentication: temporary database startup diagnostic

2026-10-22. No commit, push, deployment or production data change performed.

## Established evidence and limits

The supplied trace ends at `services/authentication.py:49:register_user`:

```python
db.session.scalar(select(User.id).where(User.email == email))
```

Login also fails at `services/authentication.py:80:authenticate`, the normalized
email user lookup on the **same SQLAlchemy engine**. Both paths therefore depend
on the same database connection, TLS settings and schema. There is no evidence
for two separate authentication logic bugs.

This is the normalized-email duplicate check, before user/workspace writes and
verification email queuing. SQLAlchemy initializes its engine during app creation
but connects lazily at this query (or a pool pre-ping). An OperationalError with no
SQLSTATE does **not** prove that PostgreSQL executed the SELECT. Connection/TLS,
DNS/network failures and a connection lost during execution are possible. A normal
missing PostgreSQL table/column instead raises a ProgrammingError with SQLSTATE
42P01/42703. Neither a missing migration nor a specific TLS failure is established
by the supplied log. Do not change authentication or run migrations speculatively.

Configuration inspection: postgres:// and postgresql:// URLs normalize to the
psycopg 3 SQLAlchemy dialect. Production requires PostgreSQL, explicit
sslmode=verify-full, bounded connections/timeouts, pre-ping and hidden SQL
parameters. The actual Render DATABASE_URL, network reachability, CA chain and
hosted schema are unavailable to this local workspace. SQLite local success does
not verify those production properties.

## Enable without Render Shell

After the operator releases the reviewed code, in **Render web service →
Environment**, temporarily set:

```text
OLUMIRA_DB_DIAGNOSTIC=1
```

Restart/redeploy through the normal operator-controlled process. Inspect Logs for
`database_diagnostic`. Copy only those sanitized entries when requesting help.
Then remove the flag or set it to `0` and restart/redeploy; do not leave it enabled.
No new public endpoint is installed. The default is off; `true` is not an alias
for `1`. Each Flask app instance probes once, even if its runner is called again. Multiple
worker app instances/restarts can emit multiple sets; with Gunicorn preload, the
probe runs before fork and closes its sockets. Configuration/driver failures are
reported early; connectivity/schema checks require successful initialization.

The probe uses the app's **same engine, runtime role, URL, CA options and timeouts**:

1. Report `database_url_configured` as a Boolean **before** validating startup
   configuration. Configuration failures report sanitized diagnostics and still
   stop startup. Driver/engine initialization failures are also reported without
   raw exceptions; successful initialization reports `driver: initialized` and a
   Boolean indicating whether the dialect is PostgreSQL.
2. Open a connection; emit connected or a sanitized failure.
3. For PostgreSQL, begin a server-enforced read-only transaction.
4. Run SELECT 1.
5. Check alembic_version existence and read revision identifiers only. Only
   repository-known revision IDs may be logged; other values become unrecognized.
6. Reflect table/column metadata and compare against the current models for
   owners, users, family_workspaces, workspace_memberships, audit_events, routines,
   routine_steps, account_tokens, email_outbox and auth_sessions.
7. Close the connection and dispose pooled sockets before a possible Gunicorn
   preload/fork. In-memory SQLite test connections are not discarded.

The probe never selects account/care records or performs INSERT/UPDATE/DELETE,
DDL, migrations or schema creation. Error logging includes only exception classes,
validated SQLSTATE, stage and fixed status hints. No raw messages, connection
strings, hostnames, usernames, passwords, tokens or SQL parameters are logged.
Missing column names come only from static model metadata. `complete:finished`
means the inspection ended, not that all preceding checks passed. Column presence
is not certification of types, constraints, grants, sequences or full migration
semantics. No SMTP or Redis probe is included in this DB-only diagnostic.

## Interpret output and apply the evidence-backed correction

| Stage/status | Meaning / next step |
| --- | --- |
| configuration / checked | `database_url_configured` reports presence only; false in production requires configuring DATABASE_URL. No value is printed. |
| configuration / failed | Startup settings failed validation; use the documented required variables. Startup remains blocked. |
| driver / initialized | PostgreSQL DBAPI/engine initialized when postgresql=true. This does not prove connectivity. |
| driver / failed | Import/driver initialization failed; restore pinned dependencies/runtime. No URL or import exception text is exposed. |
| connection / failed_tls_trust | libpq reported a trust/root-certificate error. Supply trusted roots while retaining verify-full. |
| connection / failed_tls_hostname | Certificate/hostname mismatch indication. Use the exact verified endpoint hostname; do not use an IP or internal alias. |
| connection / failed_dns | Name resolution indication. Compare URL privately to the database's current Connect information. |
| connection / failed_timeout or failed_refused | Reachability indication. Check DB availability, endpoint/port and external access allowlist for web-service outbound ranges. |
| connection / failed_authentication | Credential indication. Check runtime role credentials privately; do not post the URL. |
| connection / failed | Unclassified operational failure. Use class/SQLSTATE and provider support; do not guess or expose raw messages. |
| select_1 / ok | This startup instance actually reached and queried the DB. It does not guarantee later availability or write permission. |
| alembic_version / missing | A connection works but no version table is visible in this search path. Confirm correct database/schema before migration. |
| migration_revision / mismatch | Compare current/expected heads with the release and correct DB. Do not stamp head to conceal missing migrations. |
| registration_schema / missing_table or missing_columns | Schema visibility/model mismatch; inspect correct DB/schema, privileges and migration state. |
| all columns present / revision current | Investigate permissions, write-time failures, intermittent connections or another runtime instance using the correlated request diagnostics. |

The `failure_category` field is limited to configuration, DNS, network, TLS,
authentication, connection or SQL execution. SQLSTATE authentication/connection/
SQL classes take precedence over textual hints. Unknown connection failures remain
classified as connection; no DNS/TLS conclusion is inferred from OperationalError
alone. A read-only-transaction SQL failure is distinct from opening the connection.

Connection status hints are fixed matches of known libpq failure phrases, not a
claim of exhaustive diagnosis. An actual known SQLSTATE takes precedence over a
heuristic hint. A stage failure stops subsequent inspection; absent later entries
are not evidence that tables are missing.

### Verified TLS on Render

Render documents that internal PostgreSQL endpoints do not support verify-ca or
verify-full. Olumira's strict policy therefore requires a compatible verified
endpoint, normally Render's **External Database URL**. Preserve its exact hostname
and privately configure the runtime DATABASE_URL with:

```text
postgresql://USER:PASSWORD@EXTERNAL_HOST:5432/DATABASE?sslmode=verify-full&sslrootcert=system
```

Preserve existing query arguments using `&` and avoid duplicate sslmode/sslrootcert
parameters. `sslrootcert=system` requires libpq 16+ and a correct runtime root trust
store. The pinned psycopg binary dependency supplies libpq, but the deployed native
version/trust store still needs verification. Alternatively install an authentic
provider/CA bundle as a Render secret file and use
`sslrootcert=/etc/secrets/postgres-ca.pem`. Do not blindly trust a certificate
retrieved from the failing connection. A trusted root does not cure hostname
mismatch. Restrict external access to approved Render outbound/operator IP ranges;
do not open 0.0.0.0/0 or relax verification.

Required settings remain DATABASE_URL, APP_ENV=production, PUBLIC_APP_URL, stable
SECRET_KEY, trusted proxy configuration, shared RATELIMIT_STORAGE_URI and the
existing mail/encryption settings in [environment variables](environment-variables.md).
Do not expose MIGRATION_DATABASE_URL to web/cron processes.

### If migrations are actually missing

1. Confirm the intended database/schema and release, retain a verified recoverable
   backup, and review the additive upgrade path. Current local head is 0022.
2. Prepare an **isolated operator release environment** with the existing production
   settings, verified DB TLS, and MIGRATION_DATABASE_URL containing the separate
   schema-owner/migrator role. Its network origin must be permitted by the DB.
   This can run from an approved operator machine; Render Shell is not required.
3. From this checkout and its installed dependencies run exactly:

   ```sh
   python scripts/migrate_release.py
   ```

   The supported runner substitutes the migration URL, takes a nonblocking
   PostgreSQL advisory lock, and upgrades via Flask-Migrate. It does not downgrade,
   reset, stamp or drop tables. Review every applicable migration before execution.
4. Keep migrator credentials out of the web service. Verify the runtime role's
   existing table/sequence grants, then repeat diagnostic/readiness and an approved
   fictional signup → email verification → login. Disable the diagnostic afterward.

Do not put migrations in Gunicorn startup or use create_all/stamp/reset as a fix.
This work did not execute the release runner against production.

## Files and verification

- `olumira/database_diagnostic.py`: configuration/driver reporting, failure
  classification and once-per-app guard; opt-in setting in `olumira/config.py` and
  startup invocation in `olumira/__init__.py`.
- `.env.example`, environment-variable inventory and this procedure.
- `tests/test_database_diagnostic.py`: exact opt-in behavior, startup invocation,
  SELECT 1, absent/current/mismatched revisions, missing tables/columns, preserved
  fictional data, redaction, fixed connection statuses and mocked PostgreSQL
  read-only-before-query ordering/pool disposal.

Commands:

```sh
venv/bin/python -m pytest -q tests/test_database_diagnostic.py tests/test_registration_diagnostics.py tests/test_signup_https.py tests/test_authentication.py tests/test_account_recovery.py tests/test_infrastructure.py
venv/bin/python tests/browser/check_signup_https.py
```

Results: **74 passed** in the combined regression run (105.09s); the final
**14-test diagnostic/recovery run passed**, including transient connection failure
followed by fresh-CSRF retry and successful registration. These runs overlap.
Real HTTPS browser signup passed at 375px/1440px. The existing OpenSSL
legacy-provider warning was emitted. An initial log-capture test setup failure
(Alembic resets logging) and a recovery-fixture stale-CSRF issue were corrected;
no application CSRF checks were relaxed. `git diff --check` passed.

Real PostgreSQL reachability,
CA/hostname verification, full PostgreSQL migration/grant compatibility and the
actual hosted repair remain pending operator diagnostic output. Local migration
fixtures exercise SQLite upgrades to 0022; the PostgreSQL read-only ordering test
is a mock, not a live PostgreSQL result. Registration/auth tests exercise fictional
signup, duplicates, failure rollback/retry, verification via development queue,
login, sessions, CSRF and rate limits. No external SMTP delivery is claimed.

Sources: [Render connection/TLS documentation](https://render.com/docs/postgresql-creating-connecting#internal-connections)
and [PostgreSQL CA configuration](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-SSLROOTCERT).


## Shared login/signup follow-up verification

The new regression cases cover early configuration failure and missing URL Boolean,
driver import failure, no private values in either path, successful driver metadata,
once-per-app behavior and SQLSTATE classification priority. Existing read-only,
metadata, authentication, failure recovery and redaction cases remain. The combined follow-up run passed **60 tests** in 63.01s. The final diagnostic
run also checks SQLSTATE classes for missing tables and connection failures; its
results follow below. An existing OpenSSL legacy-provider warning was emitted. No production diagnostic
output has yet established the exact hosted failure. After the reviewed code is
released, enable OLUMIRA_DB_DIAGNOSTIC=1 in Render's web-service Environment and
save/restart. Free-tier Shell is not needed: read the startup entries in Logs.
Disable it with 0 after collecting one complete set (or its first failed stage).
Never copy unsanitized connection errors or secrets when sharing the output.

Final shared-failure diagnostic run: **21 passed** in 5.79s, including SQLSTATE
classification, once-only execution, early initialization failures and privacy.
This overlaps the 60-test combined run. `git diff --check` passed. Nothing was
committed, pushed, migrated or deployed.
