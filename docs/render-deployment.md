# Manual Render release runbook

Nothing in this repository has been deployed by Day 43. Applying `render.yaml`
creates billable web/cron resources; obtain owner authorization first. The file
is a staging template referencing an existing reviewed secret group. It does not
create databases, automatically migrate, seed data or trigger deploys on commits.
Render Blueprint schema/API validation and an actual Linux build remain pending
platform access. Python 3.14.8 availability must be confirmed before provisioning;
do not silently substitute an older vulnerable runtime.

1. Select region, budget, account owner, MFA and least-privilege access. Create
   separate staging PG17 and paid Key Value instances. Verify backups and recovery
   window in that account. Confirm paid web SMTP egress. Provision domain/sender
   SPF, DKIM and DMARC with the chosen mail provider; no real delivery authorized yet.
2. Create a schema-owner migrator and a distinct runtime role, without superuser,
   CREATEDB, CREATEROLE or replication. For a dedicated schema/database revoke PUBLIC
   CREATE, grant runtime CONNECT/database and USAGE/schema plus SELECT/INSERT/UPDATE/
   DELETE on product tables, USAGE/SELECT on sequences. Apply owner-specific default
   privileges for future tables/sequences. Permit SELECT only on alembic_version;
   revoke its runtime DML. Test runtime CRUD and denied DDL. Do not transfer ownership
   or revoke privileges on an existing shared database without reviewing impact.
3. Configure verified TLS using the external PG hostname and system trust (or
   securely installed trusted CA). Render's internal endpoint optionally uses a
   self-signed certificate; do not use sslmode=require as a workaround. Restrict
   external allowlists to reviewed service egress/operator addresses, not 0.0.0.0/0.
   Verify `pg_stat_ssl` reports SSL for the deployed connections and inspect chain/
   hostname. Use authenticated external rediss Key Value, restrict its allowlist and
   verify distributed limits across two app processes. These are external blockers.
4. Populate only the staging group from [the variable inventory](environment-variables.md).
   Keep MIGRATION_DATABASE_URL outside it. Do not enable automatic PR previews.
   Validate Blueprint in Render before applying; review proposed charges.
5. Run existing quality CI for the reviewed SHA; CI does not deploy. Inspect
   dependency/native TLS versions, test outputs and migration diff. Preserve a
   recoverable backup and record SHA, schema 0021 and operator approval.
6. In an isolated release environment with APP_ENV=production, runtime settings and
   separate MIGRATION_DATABASE_URL, run `python scripts/migrate_release.py`. It
   acquires a PG advisory lock and runs Flask-Migrate once; a second runner fails
   instead of racing. Never put migration commands in Gunicorn worker startup.
   Drain writes when compatibility is uncertain. Expanding schema must remain
   compatible with old and new instances during rolling deployment.
7. Manually deploy the approved SHA to web and cron. Start command is
   `gunicorn --config gunicorn.conf.py app:app`. One gthread worker, two threads,
   60s timeout/30s graceful drain and request recycling limit initial resources.
   Inspect memory before scaling. Build only installs pinned app requirements;
   no DB access/build-time migration. tzdata remains inherited unpinned upstream.
8. Confirm trusted Host, proxy client IP and HTTPS cookies/HSTS/redirects. Probe
   `/health/live` and `/health/ready`; only exact operational endpoints allow HTTP
   so ingress health probes cannot pass a redirect while dependencies are down.
   No private payload or credentials appear in probe responses.
9. With fictional accounts test registration/verification/recovery, dashboard,
   profile switching, routine completion, communication speech fallback,
   observation/export isolation, reminders, invitations and revoked membership.
   Actual mail acceptance/delivery requires a separately authorized test recipient.
10. Verify cron scheduling, logs/alerts, backup upload and restore. Record human
    go/no-go. Production or public demo repeats this sequence with independent
    datastores/groups; a staging pass is not real-data launch approval.

Jobs: `scripts/run_operations.py` runs process-reminders, mail-send-pending (100),
mail-retention --apply and privacy-maintenance. Each subprocess has a 240s deadline;
errors produce a failing cron run while independent maintenance still executes.
Cron is UTC every minute; reminder occurrences use existing profile timezone/DST
logic and 24h catch-up. Render serializes a given cron service; don't create a
second scheduler against the same DB. Mail uses SKIP LOCKED, max five attempts,
exponential retries and expiry. SMTP acceptance followed by process death before
commit can duplicate delivery: Message-ID is stable, but exactly-once delivery is
not promised. Tokens remain single-use. Monitor oldest pending age/attempt exhaustion;
no per-process timer or new queue is introduced. A late cron run must be retried
and investigated; maintenance never deletes care history.

Current vendor references (checked 2026-10-18):
[Blueprint fields](https://render.com/docs/blueprint-spec),
[deploy stages](https://render.com/docs/deploys),
[health probes](https://render.com/docs/health-checks),
[cron behavior/billing](https://render.com/docs/cronjobs),
[PG connections/encryption](https://render.com/docs/postgresql-creating-connecting),
[Key Value](https://render.com/docs/key-value),
[free plan limits](https://render.com/docs/free),
[Python release](https://www.python.org/downloads/release/python-3148/).
Paid pre-deploy hooks exist, but this template deliberately uses a separate
credential-isolated migration job. No persistent disk is necessary today. Render
provides TLS ingress and metrics, but selecting a plan does not configure alerts,
least privilege, recovery drills or consent/legal requirements automatically.
