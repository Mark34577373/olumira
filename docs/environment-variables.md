# Hosted environment configuration

Use separate Render environment groups for staging/production/demo. Never copy
production credentials to local tests. The template refers to an existing
`olumira-staging-reviewed` group; it deliberately contains no secret values.

| Setting | Required hosted value / scope |
| --- | --- |
| APP_ENV | `production` even in staging/demo; development/testing are local only |
| PYTHON_VERSION | `3.14.8` selected security maintenance release; verify Render availability, native TLS versions and reproducible build before approval |
| SECRET_KEY | Independent cryptographic random value, at least 32 characters |
| DATABASE_URL | Runtime DML role, `postgresql://…?sslmode=verify-full`; external verified hostname, never IP/certificate bypass |
| OLUMIRA_DB_DIAGNOSTIC | Temporary: explicitly `1` for read-only startup connectivity/schema checks. Default `0`; remove or set `0` immediately after troubleshooting. No public endpoint, account records or raw error messages. See [diagnostic procedure](render-postgres-registration.md). |
| RATELIMIT_STORAGE_URI | Authenticated external `rediss://…` with normal certificate validation; never `ssl_cert_reqs=none` |
| PUBLIC_APP_URL | Exact canonical HTTPS origin |
| TRUSTED_HOSTS | Canonical hostname(s), comma separated; default derives canonical URL; allow health-check host explicitly when necessary |
| TRUSTED_PROXY_HOPS | Explicitly `1` for standard Render web ingress; `0` for direct/local servers. Render web-service production startup rejects `0` to prevent HTTPS self-redirects. Trusts forwarded proto/for only, never Host/port/prefix; do not expose upstream port to arbitrary clients. |
| MAIL_BACKEND | `smtp` |
| MAIL_FROM | Domain-verified sender, not example.com default |
| MAIL_ENCRYPTION_KEY | Independent Fernet key; retain recovery copy in restricted vault |
| SMTP_HOST / SMTP_PORT | Reviewed provider host; 587 with starttls or 465 with ssl on paid Render |
| SMTP_USERNAME / SMTP_PASSWORD | Provider credentials, confined to this environment |
| SMTP_SECURITY | `starttls` or `ssl`, default certificate verification always enabled |
| APP_TIMEZONE | IANA timezone; default America/Chicago; cron expressions are UTC |
| AUTH_SESSION_SECONDS / AUTH_IDLE_SECONDS | Defaults 43200/1800; idle <= absolute; permitted 60–604800 seconds |
| VERIFY_TOKEN_SECONDS / RESET_TOKEN_SECONDS / EMAIL_CHANGE_TOKEN_SECONDS | Defaults 3600/1800/1800, 60–86400 permitted |
| INVITATION_SECONDS | Default 86400; 60–86400 permitted |
| PORT | Render-provided listener port, default 10000 |
| MIGRATION_DATABASE_URL | Isolated operator release job ONLY, schema-owner credentials; do not place in web/cron group |
| BACKUP_ENCRYPTION_KEY | Independent Fernet key in backup runner/vault ONLY, never mail/signing key |
| PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD/PGSSLMODE/PGSSLROOTCERT | Backup-runner libpq configuration; require verify-full, trusted CA if not system trust |

Startup validates critical app settings without exposing their values. PostgreSQL
uses pre-ping, pool size 3, overflow 1, 3-second pool/connect/lock timeouts,
300-second recycling, 10-second statements. One worker caps web connections at
four; reserve separate capacity for cron, release lock + migration (two), probes,
backups and operator sessions. Render's documented sub-8GB connection ceiling is
100, but check actual plan and leave headroom. Never increase workers without
recalculating total connection and memory budgets. Readiness queries consume a
connection; database/schema or shared-limit failure returns generic 503.

Rotation is an operator-controlled release, not an automated task: create a new
credential, test privately, update only its environment, drain old processes,
revoke old credential and verify monitoring. Signing-key rotation logs everyone
out; also revoke stored sessions if compromise suspected. Mail key rotation needs
pending-outbox re-encryption or explicit cancellation/reissue; blindly replacing
it loses pending messages. Backup keys must remain available for the whole retained
backup window; test a recovery before retiring keys. Database credential rotation
requires restarting pools; retain schema ownership in a restricted migrator role.
SMTP/API/storage rotation requires old-token revocation and reviewed rollback.
Do not log keys, place them in CLI arguments or shell history, or commit .env files.
