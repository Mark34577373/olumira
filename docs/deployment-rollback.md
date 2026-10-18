# Failed release and rollback

CI runs tests/scans only; there is no automatic deployment workflow or production
credential in GitHub. Branch protections, required checks, manual approver and
Render access must be configured by the owner. Use the tested commit SHA, record
migration revision and verified backup, then follow the manual staging release
procedure. Promote only after fictional smoke tests and a human approval.

If a new instance fails readiness, Render keeps the old deployment while rejecting
the new one (provider behavior still needs account-level verification). Stop repeated
manual retries. Inspect sanitized logs and dependency state; do not expose stack
traces or downgrade security. If application code regresses, manually redeploy the
last reviewed SHA only after checking that its code supports the current schema,
configuration and secrets. Restart cron from the compatible revision as well.

Code rollback does not undo a database migration or external mail delivery. Do not
blindly run `flask db downgrade`, edit alembic_version or restore over a live DB.
For a compatible additive migration, retain schema and roll back code. For an
incompatible/data migration, halt writes/jobs, assess a forward fix first; if recovery
is required restore separately with the backup runbook, reconcile post-snapshot
writes/closures/revocations, explicitly revoke restored artifacts and obtain human
approval before changing connection strings. Keep both source and restore until
validation and retention decisions complete. No migration rollback is claimed safe
without an isolated rehearsal.

Rollback acceptance: ready 200, trusted HTTPS/cookies, login, workspace/profile
isolation, latest known records, export scope, reminder/outbox progress and new
backup verification. Record SHA/schema/time, what was lost or duplicated, incident
owner and follow-up. Never report a rollback successful solely because HTTP loads.
