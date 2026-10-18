# Day 43 production infrastructure readiness

Assessment date: 2026-10-18. **Prepared locally; not deployed. REAL-DATA READINESS PENDING.**

## 1. Executive summary

Implemented manual staging deployment configuration, resource-aware Gunicorn,
verified PostgreSQL TLS policy/pool bounds, liveness/readiness, allowlisted JSON
request telemetry, isolated migration runner, finite operations runner and bounded
encrypted logical-backup tooling. Operational runbooks cover deployment, rollback,
recovery, environment separation, alert ownership and credential rotation. No
resources were created, charges incurred, secrets rotated, data reset, commit,
push or deployment performed. External acceptance remains blocked, not complete.

## 2. Architecture

[Audit and component inventory](production-architecture.md): existing Flask factory,
SQLAlchemy/PG17/Alembic0021, auth/CSRF/workspace/profile permissions preserved.
Browser → Render HTTPS → Gunicorn/Flask → PostgreSQL, with Key Value shared limits,
SMTP and finite DB-backed cron. No extra application framework, queue, object store,
upload system or schema migration introduced.

## 3. Hosting state

`render.yaml` is a paid staging template with automatic deployments off. It references
an independently provisioned secret group. Database/Key Value are separate reviewed
resources because runtime role, TLS host/CA and network allowlists require deliberate
setup. Local YAML parsing passed; Render API validation, Linux dependency build,
Python3.14.8 availability, domain/cert/proxy settings and real ingress remain untested.
Applying a Blueprint initially creates resources despite auto-deploy being off;
owner authorization is required before that action.

## 4. Database

Production rejects PostgreSQL without sslmode=verify-full. Runtime pool3+overflow1,
pre-ping/recycle300s, connect/pool/lock3s and statement10s. Release runner requires
separate MIGRATION_DATABASE_URL and a nonblocking PostgreSQL advisory lock. Workers
never migrate. [Release procedure](render-deployment.md) specifies DML-only runtime
role/default privileges and migrator ownership. Provider role grants/TLS and actual
connection budget remain external verification gates. No downgrade is assumed safe.

## 5. Security

Existing production secret/mail/HTTPS/cookie/CSRF/Host/rate-limit guards preserved.
Only health GET/HEAD probes bypass HTTP redirect; unsafe app requests still reject
HTTP. Request IDs are generated locally, response/probe outputs contain no internals.
Production fixture URLs now explicitly require verified certificates; negative tests
reject disable/require/verify-ca/missing mode. [Variable inventory](environment-variables.md)
separates runtime, migrator and backup credentials. No default external exception
reporter enabled. Local Python ssl still uses OpenSSL3.5.7; cryptography50.0.2 uses
OpenSSL3.6.5. The former remains a native-runtime blocker for sensitive hosting/SMTP;
verify maintained Render build/native stack rather than inferring safety from pip-audit.

## 6. Backups

[Recovery procedure](database-backup-recovery.md) proposes provider PITR plus daily
independently encrypted logical copies, 30-day provisional retention and quarterly
restore drills. Targets RPO15m/RTO4h (PITR), fallback24h/8h, **not achieved promises**.
The helper authenticates encrypted read-back, refuses overwrite and caps plaintext
memory at64MiB; separate vault/storage scheduling and lifecycle are not provisioned.
Local tests authenticate encrypted bytes and verify mode0600/wrong-key rejection.
Live PostgreSQL restore evidence is recorded below after execution; no hosted PITR,
remote encryption/upload/retention or operational recovery-time claim.

## 7. Monitoring

Live probe is dependency-free. Ready checks Alembic heads with a database query and
Redis PING when configured, returning generic503 on failure. JSON request logs use
timestamp/severity/category/operation/generated request ID/route template/status/
duration; never query/body/headers/cookies/exception text. Gunicorn access logs remain
minimized plain text. [Alert matrix](incident-response.md) defines provisional
availability/latency/error/pool/disk/job/mail/backup thresholds. No alert destinations
or on-call staff are configured; human assignment and an alert drill are blockers.

## 8. Background processing

Cron executes existing durable reminders/outbox and retention services, each command
bounded to240s, continuing independent work after a failure but exiting nonzero.
Render serializes its single cron service; no Gunicorn timer. Existing reminder
catch-up/deduplication and mail locks/retry/expiry remain. SMTP acceptance and DB
commit cannot guarantee exactly-once external delivery. DNS authentication/provider
credentials, authorized delivery test and deployed cron history remain unverified.

## 9. Deployment

[Manual release runbook](render-deployment.md): CI-required reviewed SHA, backup,
isolated one-time migration, manual staging rollout, health and fictional workflow
checks, human approval before promotion. CI now includes Gunicorn configuration
validation in addition to existing quality/security/browser gates. Remote CI and
branch/environment protection settings have not been executed/configured here.

## 10. Rollback

[Rollback runbook](deployment-rollback.md) separates compatible code rollback from
database recovery. Never downgrade blindly or restore over live data. Restore to
an empty isolated destination, reconcile post-snapshot closures/revocations, explicitly
revoke restored access artifacts, then validate before a human reopening decision.
Day42 incident response now links to these operational continuations.

## 11. Testing

Current executed evidence:

- Focused initial architecture/auth/security run:31passed,1failed because exact
  blueprint inventory needed the new health blueprint. Corrected inventory;
  architecture/infrastructure rerun14passed. Final infrastructure rerun7passed.
- `venv/bin/python -m pytest -q tests/test_infrastructure.py` covers schema/dependency
  failures, JSON redaction/request IDs, authenticated/exclusive backups, server bounds,
  verified-TLS rejection, operations failure propagation and migration lock refusal.
- `venv/bin/python scripts/check_wsgi_infrastructure.py`: real isolated Gunicorn
  live200, unmigrated-ready503, query redaction and graceful shutdown passed.
- `venv/bin/python scripts/sample_local_performance.py`: five sequential fictional
  test-client/SQLite requests per route, all expected statuses. Median milliseconds:
  login including CSRF page507.46; dashboard51.49; routines16.65; observations17.07;
  calendar83.82; reports page12.94. Tiny local dataset, no network/TLS/concurrency or
  PDF-generation timing; no production capacity conclusion.
- Local YAML structure/manual-mode checks and compileall passed. Bandit medium/high
  gate passed with zero medium/high findings. Final diff validation passed.
- Full isolated PostgreSQL run: **216 passed,29 subtests passed**,506.04s, no failures
  or skips. After formatting and three additional infrastructure assertions were
  added, focused infrastructure **7passed** in5.07s. No claim of a second full run.
- Final focused live PG run: **2passed** in8.95s. A fresh separate database was
  migrated by `scripts/migrate_release.py` to0021. The helper encrypted a real
  synthetic PG custom dump with Fernet, authenticated/decrypted it and restored
  that recovered copy into another empty database; schema0021,1board,2users matched.
  Both temporary clusters stopped successfully. TCP/TLS/provider PITR not tested.
- Expanded security coverage gate **90.86%** (target85), core **87.57%** (target80)
  passed after focused coverage refresh for the formatted infrastructure module.
- `venv/bin/python scripts/scan_secrets.py --history --output artifacts/day43/secrets.json`:
  279working files/516reachable history blobs, zero high-confidence pattern matches;
  not proof that all arbitrary credentials/remote history are absent.
- Black final check passed on eight added/refined infrastructure modules; compileall
  and Gunicorn configuration validation passed. No dependency change was made;
  dependency advisory evidence remains the dated Day41–42 run, not a new pip-audit.

Full/focused PostgreSQL invocations used:

```sh
venv/bin/python scripts/run_postgres_quality.py --bin-dir /var/folders/mg/tr1k7vxn26302_t9hywpb9m80000gn/T/olumira-postgres-qa-bybcubo7/install/bin --full --artifact-dir artifacts/day43
venv/bin/python scripts/run_postgres_quality.py --bin-dir /var/folders/mg/tr1k7vxn26302_t9hywpb9m80000gn/T/olumira-postgres-qa-bybcubo7/install/bin --append-coverage --artifact-dir artifacts/day43
venv/bin/python -m pytest -q tests/test_infrastructure.py --cov --cov-append --cov-report=json --cov-report=xml --junitxml=artifacts/day43/infrastructure-final.xml
venv/bin/python scripts/check_coverage.py
venv/bin/python -m bandit -r olumira services scripts -ll -f json -o artifacts/day43/bandit.json
git diff --check
```

The PG runner creates new disposable Unix-socket databases each invocation; those
local binary paths are machine-specific. The initial full run used the original
plain restore path; the final focused run exercised the newly encrypted restore
and isolated migration runner. Final restore details are in postgres-restore.json.

Evidence: ignored `artifacts/day43/` contains WSGI smoke, local performance and Bandit
JSON plus full-run JUnit/restore evidence. Historic coverage paths remain under
`artifacts/day41-42/`; full-run coverage replaces that generated evidence. Browser
scripts were not rerun for these backend/infrastructure changes; Day41–42 historical
browser evidence is documented separately, not claimed as a Day43 rerun.

## 12. Infrastructure costs

Provisional USD/month **budget estimates**, not a quote, account selection or purchase:
web7 + PG6–19 + KeyValue10 + cron1–7 + PG storage1.50 (5GB at estimated0.30/GB) +
SMTP0–20 + offsite storage1–10 + monitoring0–20 = approximately **$26.50–94.50**
per environment before workspace fees/tax/bandwidth/domain/restore instances. Separate
staging/production doubles applicable resources. Cron minimum$1/service/month is
verified in [current cron docs](https://render.com/docs/cronjobs). Compute figures
are estimates based on [Render pricing](https://render.com/pricing) and
[plan definitions](https://render.com/docs/compute-plans); the live pricing page's
retrieved text did not expose its full rate table, so confirm the checkout quote.
No free plan durability assumption. Paid PG recovery windows verified from
[provider recovery docs](https://render.com/docs/postgresql-backups): Hobby3days,
Pro+7days, exports7days. Workspace fees/HA and legal/provider-contract needs may
materially increase the estimate. No charge is authorized by this document.

## 13. Outstanding blockers

| Severity | Blocker / required action |
| --- | --- |
| Critical for real data | Existing privacy/consent/legal/retention/vendor review and independent security review remain pending; no real-family launch approval |
| High | No hosted deployment/TLS/CA/proxy/native-runtime verification; Render access and approved provisioning required |
| High | Runtime/migrator least privilege, network allowlists, actual Redis TLS/distributed limits and independent environment credentials unverified |
| High | No offsite backup schedule/storage/key recovery or provider PITR drill; provisional recovery targets unachieved |
| High | No verified SMTP sender/DNS/provider delivery; email verification transport not established by application token tests |
| High | No assigned operational coverage, alert recipient/drill, incident approval owner or external recovery ledger |
| Medium | Remote CI/required checks/manual approval controls and Render Blueprint validation not executed |
| Medium | Resource budget/hosted load sample and cron capacity need measurement before scaling or beta traffic |
| Low | Current tzdata requirement remains unpinned; fully reproducible native dependency/SBOM review remains work for release |

## 14. Day 44 readiness

Ready to continue **local fictional-data** beta preparation with recorded limitations.
A hosted fictional beta still requires approved resources, successful staging release,
verified email flow, separation/access restrictions and working operational alerts.
No hosted beta readiness claim is made by local tests alone.

## 15. Real-data readiness

**REAL-DATA READINESS PENDING.** Existing [formal readiness checklist](real-data-readiness.md)
remains authoritative. Infrastructure preparation does not grant launch approval.

Suggested commit after human review only:
`chore(infra): complete Olumira day 43 production infrastructure`.
