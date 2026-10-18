# Backup and recovery procedure

Status: local synthetic recovery evidence only. No scheduled external backup or
storage resource exists. Render paid PG provides continuous recovery; current
[provider documentation](https://render.com/docs/postgresql-backups) says Hobby
PITR covers three days, Pro+ seven days; latest ten minutes are not selectable.
Logical exports remain available seven days. Free PG has no provider recovery.
Deleting an instance deletes its provider backups: independent retention matters.

Provisional, unachieved targets: provider recovery RPO <=15 minutes and RTO <=4h;
independent daily-backup fallback RPO <=24h, RTO <=8h. Outage and corruption may
change these targets. Measure actual time and loss in a hosted drill, including
identity/authorization checks, before promising them.

Proposed independent policy, pending owner/privacy approval: daily encrypted
logical backup, 30-day rolling retention, monthly retained copies only if justified;
quarterly isolated restore drill and after major schema/key changes. Dedicated
backup identity has table read/sequence read only, no public app credentials.
Store encrypted output in an independently controlled bucket with TLS, server-side
encryption, restricted writer/read roles, versioning and immutable retention.
Keep the client encryption key in a separate restricted vault with recovery access.
Alert on missing upload after 26h, authentication failure, lifecycle drift or
restore failure. Do not treat local ephemeral output as a backup destination.

`python scripts/encrypted_backup.py --output <new-private-path>` uses explicit
libpq environment settings and pg_dump custom format with no owner/ACL. It requires
verify-full, a separate Fernet BACKUP_ENCRYPTION_KEY, exclusive 0600 destination,
64MiB unencrypted dump limit and authenticated read-back. It never overwrites,
uploads, deletes old backups or prints credentials. It buffers the bounded dump
in memory; it is for small beta databases only. Larger databases need a reviewed
streaming managed backup path, not a raised arbitrary memory ceiling. Use matching
PG17 client tools and runner memory headroom. Run the backup runner under a hard
external timeout (e.g. 5 minutes) as well. No plaintext backup is written by this
helper; encrypted output is sensitive too. Production scheduling/upload/lifecycle
are blocked on authorized storage/provider credentials and must be verified.

Restore into a **new empty isolated database only**:

1. Stop traffic/writers/mail/cron, preserve source and incident evidence. Select
   the appropriate PITR point or authenticated encrypted backup and verify age.
   Record source SHA/schema/key ID privately. Never pass passwords in argv/history.
2. For PITR create a new provider instance. For an encrypted logical copy, retrieve
   its separate key and authenticate/decrypt using Fernet into a 0600 temporary file
   within a 0700 directory on a reviewed encrypted recovery disk. Never print bytes.
   Wrong-key/tampering must fail before pg_restore runs.
3. Inspect with `pg_restore --list` privately. Confirm target host/database identity
   twice, block application connections and verify no product tables exist. Run
   `pg_restore --exit-on-error --single-transaction --no-owner --no-acl --dbname=<new-name> <private-dump>`
   using separate libpq credentials. Do not use --clean against existing data.
4. Compare Alembic revision, all table counts, constraints, representative fictional
   relations and sequence advancement. Apply only reviewed forward migrations with
   the isolated runner. Reestablish runtime role grants and TLS/network restrictions.
5. Follow [Day 42 containment/recovery](day42-security-review.md#recovery-incident-response-and-day-43-handoff):
   rotate potentially compromised credentials, explicitly revoke restored access
   artifacts and reconcile membership revocations/closures since the snapshot from
   the externally retained ledger. Restoring care data must not resurrect access.
6. Test health/schema/Redis, login and recovery, family/profile isolation, reports,
   queues/reminders. Independently verify backup encryption and offsite access.
   A named human authorizes traffic reopening. Switch runtime URL, restart pools,
   watch error/queue metrics. Preserve old source for the approved evidence window.
7. Record elapsed recovery, observed data loss, deviations and follow-ups. Safely
   remove temporary decrypted files according to encrypted-volume policy; ordinary
   unlink is not a forensic erasure guarantee. Keep encrypted retained originals.

Local evidence uses a fresh Unix-socket PostgreSQL cluster, no TCP/TLS or provider
credentials. It verifies dump/restore, schema and selected counts, not provider
PITR, encrypted remote storage, real-volume recovery time or complete retention.
See Day 43 report for exact current executed results.
