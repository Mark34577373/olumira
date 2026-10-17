# Day 16 — verification, recovery, settings, and sessions

## Scope and checkpoint

Built on the Day 15 factory, authentication blueprint, CSRF, rate limiting, salted password hashes, server-checked sessions, and private account/owner mapping. The baseline run discovered 41 tests: 40 passed and one live PostgreSQL test was skipped. Existing changes were preserved.

Day 16 adds working email verification, recovery, account settings, verified-email access rules, credential-generation/session revocation, and a private development email workflow. No production emails, hosted migrations, push, commit, or deployment were performed.

## Implemented behavior

- Registration creates an unverified account, queues verification, and does not sign the user in automatically.
- Verified email is required for **all five caregiver application blueprints**, including state-changing requests. Unverified users may sign in only for verification, account settings, and logout. Existing unverified accounts are not silently grandfathered into verified access.
- Verification uses a purpose-bound, expiring, single-use code. GET never consumes a code, so email link scanners cannot verify an account. Successful verification ends existing limited sessions; the user signs in again.
- Public forgot-password and resend-verification forms use generic confirmations for known/unknown addresses, invalid addresses, already-verified accounts, and queue failures. They do not wait for SMTP. No reset request authenticates a user or changes a password.
- Reset validates the code, purpose, recipient snapshot, expiry, credential generation, and single use, then updates the salted password hash, cancels all outstanding account links/pending email changes, revokes all sessions, and queues a password-changed notification atomically. It does not automatically verify an unverified email or sign in the user.
- Settings allow display-name updates, password changes, new-email verification, cancellation of a pending email change, and sign-out everywhere. Every sensitive operation requires the current password again, in addition to the authenticated session and CSRF. Only the current server-authenticated user ID is used.
- A pending email never replaces the primary address until its own confirmation succeeds. Database email uniqueness protects confirmation races. Confirmation verifies the new address, revokes sessions and old links, and queues notifications to the new address and the previously verified old address. An unverified old address is not sent a change notification.
- Sign-out everywhere revokes sessions, increments the credential generation, cancels pending account links/email changes, and clears the current cookie. It is a real action; no device-list UI is invented.
- Login captures the credential generation it actually checked; session creation locks and rechecks it. This closes the login/reset race where an old-password check might otherwise create a new session after a reset. Loaders reject stale generations even if a session record has not yet been marked revoked.
- The account/settings/recovery pages reuse the existing forest/sage components, original local illustration, horizontal navigation, focus states, error/status messages, and responsive spacing. Form inputs disable spellchecking/autocapitalization to avoid altering or submitting sensitive codes/passphrases through enhanced spellchecking.

## Tokens and migration

Revision `0003_account_recovery` is additive to `0002`:

- `users.pending_email` and non-null `users.auth_version` (default 0).
- `auth_sessions.auth_version` (default 0).
- `account_tokens`: SHA-256 token digest, user FK, checked purpose, target-email snapshot, credential generation, issued/expiry/used timestamps.
- `email_outbox`: encrypted message payload, user/token references, kind, scheduling/expiry, attempts, delivery/cancellation times, generic failure code. No raw recipient/message/token is written into delivery logs.

Account codes have 256 bits of cryptographically random entropy. Only digests are stored in the verifier table. The outbox necessarily retains deliverable link material, encrypted with the maintained `cryptography` Fernet implementation and a separate production key. It contains no plaintext tokens. A database-only compromise does not reveal queued link bodies without that key; a full application-host/key compromise is outside that protection.

Consumption locks the account and token and conditionally updates an unused, unexpired code inside the same transaction as the change. Purpose and account-generation checks prevent cross-purpose use or stale-link replay. Resending cancels earlier links of the same purpose and their unsent emails. Credential changes cancel every outstanding account link. Existing routine, observation, account, and session records are preserved by the migration; upgrade tests cover populated Day 15 account data and repeatable upgrades.

Created a verified ignored source snapshot `database/backups/pre-day16-20261016.db`: 4 owners, 20 routines, 0 observations, 3 completion rows. The original local database was not stamped, migrated, or reassigned. The current migration head is **0003**. Unversioned legacy SQLite still needs backed-up baseline adoption before upgrade. The legacy-only transfer command requires an empty 0003 target and refuses source/destination account, token, session, or mail data rather than silently omitting it.

## Email delivery architecture

HTTP account operations write an encrypted transactional outbox; they never connect to SMTP. This keeps transport failures/latency out of recovery responses, supports retry, and commits notifications with credential changes. Unknown-address requests do local cryptographic work and receive the same visible confirmation. No mathematically constant-time HTTP claim is made.

Delivery is an explicit scheduled worker:

```sh
venv/bin/python -m flask --app app mail-send-pending --limit 20
```

Run this command every minute using an approved scheduler/Render cron job with the **same database and encryption key** as the web service. PostgreSQL workers use row locks with `SKIP LOCKED`; run only one worker when using local SQLite. Messages use authenticated SMTP over mandatory STARTTLS or implicit TLS with certificate verification. There is no plaintext fallback. The worker never enables SMTP debug logging.

Failures log only a generic message, record `delivery_failed`, and retry with 1/2/4/8-minute backoff, up to five attempts. Expired/used/cancelled link emails are skipped. Exhausted jobs remain visible in queue metadata for operator review. Delivery is **at least once**: a crash after SMTP acceptance but before database commit may cause a duplicate email; stable Message-ID helps clients recognize duplicates, while the account code remains single-use. SMTP acceptance is not proof of inbox delivery. Sent/expired encrypted payload retention is not automatically purged; set an approved retention policy before production.

`mail-queue` prints only message ID, purpose, state, and attempt count. It does not print addresses, codes, subjects/bodies, credentials, or provider exceptions.

## Local development and email preview

Development defaults to `MAIL_BACKEND=development`, queues encrypted messages, and **sends no real email**. Authentication pages identify this local preview mode so an inbox delivery is not falsely implied. The encryption key is derived from the local signing key only as a development fallback; use fictional accounts in this mode. Production requires an independent explicit Fernet key.

From the repository root, with the intended local database configured:

```sh
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m flask --app app db upgrade
venv/bin/python -m flask --app app db current
venv/bin/python -m flask --app app run --port 5050
```

If the database has existing unversioned tables, follow [baseline adoption](database-migration.md) first; do not run initial table creation over it or blindly stamp a revision. Stop old Flask processes and restart after migration. `gunicorn app:app` remains the deployment entry point.

1. Register a **fictional** account at `/auth/register`.
2. Inspect queue metadata and create a private email file:

```sh
venv/bin/python -m flask --app app mail-queue
venv/bin/python -m flask --app app mail-preview \
  --message-id <id-from-mail-queue> \
  --output database/mail-preview/verification.eml
```

3. Open the `.eml` locally and follow its link. Preview files are created exclusively with mode 0600, never overwritten, ignored by Git, and unavailable through a web route. The CLI does not print link contents. Use a new filename for each preview.
4. Confirm verification, then sign in. All caregiver pages should now be available.
5. Request recovery at `/auth/forgot-password`, preview the new message, and choose a new password. Earlier sessions and recovery links must stop working.
6. Open `/auth/settings`, change the display name, then request a new email. The old address remains primary until confirmation. Preview the new-address email, confirm, and sign in with the new address.
7. Review password changes, pending-email cancellation, and sign-out everywhere. Each sensitive settings action asks for the current password.

The default public URL is `http://127.0.0.1:5050`. Set `PUBLIC_APP_URL` if using a different origin/port. Generated links never use an incoming Host header. Links carry the secret in a URL **fragment**, not a query or path; the fragment is never sent in HTTP requests. The local script fills the form and removes the fragment from history. Without JavaScript, paste the emailed code into the labelled field. Codes are not stored in localStorage/sessionStorage. Referrer-Policy remains `no-referrer`; pages remain `no-store`.

## Configuration

Existing Day 15 settings remain: production PostgreSQL `DATABASE_URL`, shared Redis `RATELIMIT_STORAGE_URI`, strong stable `SECRET_KEY`, trusted proxy count/hosts, secure cookies, session timeouts, and application timezone.

| Setting | Requirement / default |
| --- | --- |
| `PUBLIC_APP_URL` | Canonical origin, no credentials/query/fragment/path prefix; HTTPS required in production |
| `MAIL_BACKEND` | `development` locally; `smtp` required in production |
| `MAIL_FROM` | Provider-verified sender, e.g. `Olumira <no-reply@your-domain>` |
| `MAIL_ENCRYPTION_KEY` | Independent Fernet key required in production; keep stable and back up separately from DB |
| `SMTP_HOST` | Transactional provider's SMTP hostname |
| `SMTP_PORT` | 587 by default; typically 465 with implicit TLS |
| `SMTP_SECURITY` | `starttls` (default) or `ssl`; plaintext delivery is rejected |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Required provider SMTP credentials in production |
| `VERIFY_TOKEN_SECONDS` | 3600 (60 minutes) |
| `RESET_TOKEN_SECONDS` | 1800 (30 minutes) |
| `EMAIL_CHANGE_TOKEN_SECONDS` | 1800 (30 minutes) |

All token lifetimes must be 60–86400 seconds. Testing always selects the no-delivery development backend. SMTP behavior tests explicitly mock the transport; automated tests do not send real email.

Generate a production encryption key privately, then place it only in the deployment secret store:

```sh
venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Do not put the key or real credentials in source, screenshots, issue descriptions, or logs. Losing/rotating the key makes old queued payloads unreadable; arrange a controlled drain/cancel/resend and backup plan rather than silently discarding mail. It does not change password hashes or account-token digests.

Recovery and resend are limited to 5/hour per IP and 3/hour per normalized account bucket; link submission is limited to 10/hour per IP. Sensitive settings are limited to 10/hour per IP **and account**, in addition to password reauthentication. Limits use shared Redis in production; no fallback to per-process memory is permitted. Correct trusted-proxy configuration is required. No user email address is used as a plaintext limiter key.

## Verification and artifacts

Final results:

- `venv/bin/python -m unittest discover -s tests -v`: **62 discovered, 61 passed, 1 skipped** (live PostgreSQL unavailable). Includes a populated 0002-to-0003 upgrade preserving password hashes, verification state, owners/routines, and existing session rows; model/migration agreement and repeated upgrades also pass.
- The **20 account-recovery/email tests** were rerun after final email-header refinements: all pass. SMTP is mocked; this is not live delivery verification.
- `tests/browser/check_ui.py`: **42 page/viewport checks passed**, plus registration → actual email-code verification → login, previous workflows, keyboard/mobile behavior, two-account isolation, and no-JavaScript sign-in. No overflow or console/page errors.
- `tests/browser/check_accounts.py`: **42 additional page/viewport checks passed**, plus unverified access restrictions, manual verification without JavaScript, display-name change, pending/confirmed email changes, fragment removal, keyboard confirmation, forgot/reset flow, sign-in with the new address/password, and session termination after password changes. No unexpected console/page errors or overflow. Expired email-change recovery correctly leads to authenticated settings instead of the unrelated primary-address resend form.
- `pip check`, `gunicorn --check-config app:app`, and `git diff --check` pass. Actual HTTP startup is exercised by the isolated browser servers.
- Original legacy records were re-read and compared with the Day 16 recovery snapshot: unchanged. Git index remains empty; local databases, private email previews, and browser artifacts are ignored. No commit/push/deployment. Existing application tests, Day 15 security tests, and Day 16 tests all use isolated fictional data. New cases cover expiry, invalid/wrong-purpose/replaced/used codes, verification gates, canonical URL construction, generic messages, encryption/private preview, settings authorization, current-password checks, confirmation-only email changes, credential-generation races, session revocation, mail retry/redaction, and mocked TLS SMTP.

Two Playwright suites render all application and account pages at 1440, 1280, 1024, 768, 390, and 320px:

```sh
venv/bin/python -m unittest discover -s tests -v
venv/bin/python tests/browser/check_ui.py
venv/bin/python tests/browser/check_accounts.py
venv/bin/python -m pip check
venv/bin/gunicorn --check-config app:app
```

Screenshots and JSON reports are in ignored `artifacts/after-day16/` and `artifacts/day16-accounts/`. The tests read only their own encrypted synthetic inbox, never production mail, and redact link secrets from error output. Desktop settings and mobile password-recovery images were inspected directly. Tests cover both automatic fragment filling and no-JavaScript code entry, keyboard confirmation, settings, recovery, and old-session rejection, as well as previous routine/observation/communication/resource workflows.

No live PostgreSQL, Redis, transactional provider, or real mailbox was available. PostgreSQL migration SQL is generated offline and checked; live integration remains a deployment gate. No inbox-delivery or formal security/WCAG certification claim is made. Broader browser, assistive-technology, email-client rendering, and production concurrency/load review remain outstanding.

## Production rollout and recovery gate

Before an explicitly approved deployment:

1. Verify the sending domain/provider, SPF/DKIM/DMARC, sender policy, TLS SMTP host/port, and approved test recipient. Configure secrets privately. Disable link rewriting/click tracking, open tracking, and message-body/debug capture for these security emails; verify the provider preserves fragment links without recording their secrets.
2. Back up and verify the database and the separate encryption key. Review the 0003 migration; stop traffic/writes for the approved cutover.
3. Run tests against disposable PostgreSQL/Redis and a provider sandbox/approved test mailbox. Confirm tokens and private data do not appear in edge, proxy, app, worker, provider-debug, or monitoring logs.
4. Apply the reviewed migration once; deploy the same code/config to web and scheduled email worker. Confirm the canonical HTTPS origin, secure cookie flags, CSRF, and proxy trust.
5. Smoke-test registration → verification → sign-in; unknown/known recovery messages; reset expiry/reuse; changed password/new email; sign-out everywhere; cross-account isolation; retries and queue monitoring. Verify actual inbox arrival before claiming live email works.
6. Keep rollback backups and a maintenance path. Do not restore over the only recovery copy or remove account tables automatically. Old pre-authentication code must not be exposed against account-bearing databases. Rolling back to Day 15 removes verification gating and does not understand credential generations; keep traffic blocked until an approved compatible recovery is complete.

No hosted migration, credentials, worker scheduling, SMTP transmission, commit, push, or deployment was performed by this task.

## Files and dependency

- New migration: `migrations/versions/0003_account_recovery.py`.
- New services: `services/account_recovery.py`, `services/email_delivery.py`.
- New CLI: `olumira/mail_commands.py`.
- Updated models/config/integration: `olumira/models.py`, `olumira/config.py`, `olumira/__init__.py`, `olumira/forms.py`, `olumira/routes/auth.py`, `services/authentication.py`, `services/data_transfer.py`.
- New UI: `templates/auth/{message,request_link,verification,use_link,settings}.html`; updated shared auth layout/field/login and header; local CSS/JS refinements.
- New emails: branded HTML and text alternatives for verification, reset, new-email confirmation, password changed, email changed; shared HTML email base.
- New verification: `tests/test_account_recovery.py`, `tests/browser/check_accounts.py`; updated existing fixtures, architecture/migration tests, and app browser suite.
- Setup/docs: requirements, `.env.example`, `.gitignore`, README, migration runbook, this checkpoint.
- New direct dependency: **cryptography 47.0.0** for maintained authenticated payload encryption. SMTP uses Python's standard library; no frontend framework or external scripts were added.

Suggested commit: `Day 16: Add account recovery and email verification`.

Design references: official [OWASP password recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html), [Fernet documentation](https://cryptography.io/en/latest/fernet/), and [Python SMTP/TLS documentation](https://docs.python.org/3/library/smtplib.html).
