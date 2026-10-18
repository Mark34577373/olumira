# Day 43 infrastructure audit and architecture

Reviewed 2026-10-18. Status: locally prepared; no Render resources or deployment.

The factory in `olumira/__init__.py` constructs Flask, SQLAlchemy, Flask-Migrate,
Flask-Login, CSRF and shared rate limiting. `app.py` exposes `app:app`. Thirteen
product blueprints now share a separate operational health blueprint. Alembic
head is 0021; startup does not create tables, migrate or seed. Existing reports:
[Day 41](day41-quality-report.md), [Day 42](day42-security-review.md),
[real-data gates](real-data-readiness.md). Previous evidence is historical, not a
substitute for Day 43 execution.

Before this change there was no deployment manifest, dependency readiness probe,
bounded production pool or complete release/restore procedure. Existing controls
already reject production SQLite, weak secrets, debug mode, development SMTP,
memory limits and insecure cookies. New work adds verified PostgreSQL TLS,
bounded pools, operational probes/telemetry, reviewed Gunicorn defaults, manual
Render configuration, an isolated migration runner and encrypted backup helper.
Implementation order: configuration/probes, deployment/jobs, recovery, regression
verification. No schema change is needed.

| Component | Purpose/data | Controls and failure/recovery | Cost/status |
| --- | --- | --- | --- |
| Paid Render web | HTTPS, private care requests | TLS ingress, strict Host/proxy, one Gunicorn worker/two threads; unhealthy deploy refused, rollback reviewed revision | Required; estimate $7/month |
| Paid managed PostgreSQL | All persistent account/workspace/care/outbox data | Verified TLS, bounded pool, runtime DML role; isolated migration role; PITR/new-instance recovery | Required; plan unselected |
| Paid Key Value | Rate-limit keys; no care document cache | External TLS `rediss://`, auth/network allowlist; fail closed on outage, monitor restarts | Required for production; estimate $10/month |
| Finite Render cron | Durable DB mail/reminder and retention commands | Same environment, single active scheduled run; transaction locks/retries; nonzero exit monitored | Required; $1/month minimum plus runtime |
| Authenticated SMTP provider | Recipient and verification/recovery message | Verified sender, TLS certificate checks, encrypted outbox, limited retries/expiry; credentials/transport still untested | Required; estimate $0–20/month at beta volume |
| Backup storage | Encrypted sensitive DB copies | Separate key/access boundary, immutable storage/lifecycle, authenticated restores; provider deletion must not delete independent copies | Required before real data; estimate $1–10/month |
| Monitoring | Allowlisted telemetry/availability | No bodies/queries/cookies; restricted retention; external integrations disabled until privacy review | Required operator setup; estimate $0–20/month |
| Object storage / queue / dedicated worker | Future private uploads or sustained job traffic | Not currently needed; no upload routes; DB outbox already durable | Not provisioned |

There are no persistent user-upload files today. Static SVG assets are deployed
with code. PDF/CSV/JSON exports are generated in memory. Ephemeral web/cron disk
is never a durable private file store. Local SQLite backups and mail previews
remain local operator tools, unavailable in production.

Development uses local SQLite and private mail previews; automated tests use
fresh isolated SQLite/PG and guard real SMTP. Staging, production and optional
public fictional demo must each have separate paid datastores, signing/mail keys,
SMTP credentials and environment groups. All hosted copies use APP_ENV=production
security. An environment's name is not a privacy boundary: web URLs remain public.
Do not load real data into any preview/demo or attach production groups to PRs.
Disable automatic preview environments. A private beta additionally needs reviewed
access restrictions and invited fictional testers; registration alone is not
network privacy. No real-family collection is enabled or approved by this work.
