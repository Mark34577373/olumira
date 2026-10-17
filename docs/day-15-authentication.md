# Day 15 — authentication review checkpoint

## Audit and implementation plan

Inspected the factory, all five blueprints, services, models, migrations, templates, static scripts, configuration, deployment entry point, and tests. The pre-change suite discovered 21 tests: 20 passed, one live PostgreSQL test skipped. Days 12–14 changes were already present; they were preserved.

Security gaps identified: no user model, authentication, CSRF, or throttling; the signed visitor cookie selected an owner; custom communication choices used a shared browser-storage key. The existing ownership predicates in routine/observation services were retained, but their source of authority needed replacement.

Plan executed: additive account/session migration; account-to-owner mapping; registration and password hashing; Flask-Login with revocable server-side session checks; CSRF on all POST forms; bounded authentication attempts; protected application blueprints; branded account UI; isolated security and browser tests. Day 16 is deliberately NOT started: the master prompt says “Stop at the Day 15 checkpoint for review.”

## Implemented

- `users`: UUID identifier, canonical unique email, salted password hash, display name, verification flag, UTC creation/update timestamps, unique non-null owner FK.
- `auth_sessions`: SHA-256 digest of a cryptographically random 256-bit session handle, user FK, issuance, absolute expiry, last-seen and revocation times. No raw handle is stored in the database.
- Revision `0002`, additive to baseline `0001`; it does not alter, delete, or reassign existing records. Downgrade refuses destructive table removal.
- Registration with field-level validation, email normalization, database uniqueness (including concurrent duplicate handling), password confirmation, and a separate sign-in step.
- Werkzeug scrypt hashing with N=131072, r=8, p=1; random salts; 15–128 characters; no composition rules; stored-hash parameter upgrades after successful authentication. Passwords are never truncated, logged, echoed into forms, or put in URLs. A small offline common-choice guard exists; this is not a complete compromised-password corpus or a remote breach check.
- Login with generic credential failures, dummy-hash verification for unknown accounts, allowlisted return paths, cleared pre-authentication cookie state, renewed authentication handle, and fresh Flask-Login authentication.
- POST/CSRF-protected logout revokes the active server record. Replaying the old signed cookie after logout is rejected.
- Twelve-hour absolute and thirty-minute idle expiry by default. Server checks override sliding cookie lifetime. Last-seen writes are throttled to one per minute, making idle expiry conservative by at most one minute. A service function to revoke every session is ready for Day 16 credential changes; no device-list UI is claimed.
- All five application blueprints require authentication. Every route receives its owner only from the authenticated user record. All existing routine/observation queries and mutation predicates remain owner-scoped.
- New registrations create an entirely new owner and starter routines atomically. Legacy visitor cookies, old owners, and unowned records cannot be claimed through the UI. Old records are preserved and quarantined until a deliberate future ownership migration.
- Global Flask-WTF CSRF, including existing routine and observation forms. Login CSRF secrets rotate with the cleared authentication session. Invalid/expired forms get a branded refresh message.
- Flask-Limiter: login 10/minute and 100/hour per IP, plus 20/hour per normalized account; registration 5/hour per IP. Account bucket identifiers are HMACs rather than raw email addresses. Production requires Redis storage; errors do not fall back to per-process memory. Local development/tests use memory storage.
- HttpOnly/SameSite cookies; enforced Secure, host-only `__Host-` cookies in production; no-store HTML, no-referrer, frame denial, nosniff, production HSTS, and a self-hosted-script CSP. Existing inline delete confirmation was moved into the local script to retain its behavior under CSP.
- Forest/sage login and registration pages, password visibility controls, autocomplete, labels, accessible errors, account-menu keyboard/Escape support, and functional sign-out. No settings or recovery links are shown before they work.
- Custom communication options use an account-specific browser-storage namespace. Old shared browser choices are not imported into new accounts. Authentication is never stored in localStorage.

## Verification

Final execution:

- `venv/bin/python -m unittest discover -s tests -v`: **41 discovered, 40 passed, 1 skipped** (no live PostgreSQL instance). Includes registration, duplicate race rollback, hashing/upgrades, login/logout, CSRF, IP/account throttling, cookie flags, idle/absolute expiry, all-session revocation, stale-cookie replay, identity/handle mismatch, safe redirects, legacy/cross-account isolation, sanitized logging, migrations, model agreement, import rollback, and existing workflows.
- `venv/bin/python tests/browser/check_ui.py`: **42 page/viewport combinations passed**, plus registration/login/logout, password visibility, keyboard/mobile/account-menu behavior, existing workflows, second-account observation and custom-board isolation, and quarantine of old browser choices. No horizontal overflow or JavaScript console/page errors. Existing sampled application text contrast checks passed.
- `venv/bin/python -m pip check`: no broken requirements.
- `venv/bin/gunicorn --check-config app:app`: passed; actual HTTP startup exercised by the isolated browser server.
- `git diff --check`: passed. No staged files, commits, pushes, or deployment.
- Re-read the original database and compared all four legacy tables with the Day 15 snapshot: unchanged.

A new logging regression test exposed Alembic's default logging setup disabling existing application loggers. `migrations/env.py` now preserves existing loggers; the final sanitized-error logging tests pass after migration execution. Test accounts and browser observations are fictional and live only in temporary databases. No automated test sends email.

The browser run renders login, registration, and all five application pages at 1440, 1280, 1024, 768, 390, and 320px. It covers actual registration/sign-in, password visibility, protected pages, keyboard navigation, routine completion, observation save/dashboard update, communication selection/custom persistence, resource filters/details, account-menu Escape, logout, and no-JavaScript sign-in/navigation. Screenshots are in ignored `artifacts/after-day15/`. Desktop login and narrow-mobile registration images were visually inspected.

## Backup and migration status

Created verified ignored snapshot `database/backups/pre-day15-20261016.db`: 4 owners, 20 routines, 0 observations, 3 completion rows. The original database was not stamped or migrated by Day 15. This snapshot reflects the source at this milestone, which has more visitor records than the historical Day 13 snapshot.

Before serving the new code, install requirements and run the versioned migration on the intended local database. For a baseline-managed database:

```sh
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m flask --app app db upgrade
venv/bin/python -m flask --app app db current
venv/bin/python -m flask --app app run --port 5050
```

Expected revision: `0002`. For an unversioned legacy SQLite file, first use the backed-up `adopt-legacy-sqlite` procedure in the database runbook; that stamps only `0001`, then upgrade adds `0002`. Do not run baseline creation over existing tables or bypass schema validation with a blind stamp. The application never performs migrations on startup.

The legacy transfer command now requires empty migrated revision `0002` destinations and refuses nonempty account/session tables or a source containing account records. It must not silently discard newly created accounts. Migrating a populated account database across database engines needs an account-aware reviewed process; legacy-only transfer is not that process.

## Required configuration

Existing: `APP_ENV`, stable random `SECRET_KEY`, production PostgreSQL `DATABASE_URL`, `APP_TIMEZONE`.

New:

| Setting | Default / requirement |
| --- | --- |
| `AUTH_SESSION_SECONDS` | 43200 (12 hours); maximum seven days |
| `AUTH_IDLE_SECONDS` | 1800 (30 minutes), at least 60 seconds and no longer than absolute lifetime |
| `RATELIMIT_STORAGE_URI` | `memory://` locally; `redis://` or `rediss://` required in production; use provider-required TLS |
| `TRUSTED_PROXY_HOPS` | 0; set to the exact trusted proxy count (1 or 2 supported) only when direct access is prevented |
| `TRUSTED_HOSTS` | Comma-separated accepted production hostnames; configure for the intended hostname(s) |

Production additionally requires at least 32 characters for the secret, enforces CSRF/rate limiting and secure cookie flags, and forbids debug/testing. Use a random secret, not a human-generated 32-character phrase. Memory limits are for a single local process, not a production deployment. Rate limiting without correctly reviewed proxy configuration can throttle an entire proxy or allow spoofing; never trust arbitrary forwarded headers.

No email configuration is added yet. Verification flags default to false; Day 15 permits unverified accounts to sign in to their own isolated data. Email delivery, verification enforcement policy, recovery, settings, and credential-change notifications remain Day 16 work. Do not treat this checkpoint as the completed Days 15–16 release.

## Manual local review

1. Use a migrated local database and restart Flask; visit `/auth/register`.
2. Register a fictional email with a unique 15+ character passphrase; confirm sign-in is required afterward.
3. Sign in, toggle a routine, and save a fictional observation; reload to check persistence.
4. Use the account menu to sign out; direct application URLs must return to sign-in.
5. Register/sign in as a second fictional account; the first account's saved observation and custom communication cards must not appear.
6. Use keyboard only through fields, password toggles, mobile/account menus, and sign-out. Review layouts at six documented widths.
7. Confirm no credentials, session handles, or submitted observations appear in application logs.

## Production setup and smoke-test gate

No deployment, hosted migration, account creation on a remote service, or production test has been performed. PostgreSQL and shared Redis were not available for live integration testing here. Before an approved deployment:

- Finish and review Day 16, including actual email delivery configuration and verification/recovery policy.
- Configure the signing key, PostgreSQL, shared Redis, trusted hostnames, proxy count, and HTTPS cookies; keep credentials out of source and logs.
- Create and verify restricted backups; validate the current Alembic revision and review the additive migration SQL.
- Run tests against disposable PostgreSQL and Redis services, then approve the hosted migration/cutover.
- Smoke-test registration, credential failures, throttling across workers, cookie flags on HTTPS, expiry, logout-cookie replay, CSRF rejection, return URLs, and two-account isolation.
- Benchmark scrypt on the deployment instance: each operation uses roughly 128 MiB, so set worker/concurrency capacity accordingly. Do not silently lower hashing cost to fit an undersized instance.

If a migration/cutover fails, keep the service in maintenance mode and preserve source/backups. Do not roll back to the old unauthenticated application while exposing a database containing account data. Account-table removal, overwriting data, hosted migrations, and restoration require an approved recovery plan. Expired/revoked session rows are not automatically deleted; retention/cleanup needs a reviewed policy.

## Known limitations

No real email delivery, verification/reset tokens, password recovery/change UI, account settings, MFA, full device-session UI, family permissions, or comprehensive compromised-password check is implemented in Day 15. No formal security audit, penetration test, or WCAG certification is claimed. Browser-local communication choices are namespaced for account separation in the application, but are not encrypted against someone with access to the browser profile/devtools; server-backed boards remain future work. A stolen still-valid cookie is a bearer credential until expiration/revocation. Signed cookies are authenticated, not encrypted, and contain an opaque handle plus Flask-Login/CSRF metadata; every protected request must also pass the database-backed session check.

## Changed files and dependencies

- Accounts/session persistence: `olumira/models.py`, `migrations/versions/0002_user_authentication.py`, `services/authentication.py`.
- Integration: `olumira/__init__.py`, `olumira/config.py`, `olumira/extensions.py`, `olumira/forms.py`, `olumira/routes/auth.py`.
- UI: `templates/auth/{layout,login,register,_field}.html`, `templates/base.html`, existing POST form templates, `static/css/style.css`, `static/js/app.js`, communication storage scope.
- Migration/logging compatibility: `services/data_transfer.py`, `migrations/env.py`; existing baseline adoption retains its original strict checks.
- Tests: `tests/test_authentication.py`, `tests/support.py`, existing architecture/persistence/UI tests and browser script.
- Setup/report: requirements, `.env.example`, README, database runbook, this checkpoint.
- New direct dependencies: Flask-Login 0.6.3, Flask-WTF 1.3.0, Flask-Limiter[redis] 4.1.1, email-validator 2.3.0. Existing Werkzeug provides scrypt; no custom cryptography is implemented.

Suggested commit: `Day 15: Implement secure Olumira user authentication`.

Security decisions were checked against the official [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [session management guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [Flask-Login documentation](https://flask-login.readthedocs.io/en/latest/), [Flask-WTF configuration](https://flask-wtf.readthedocs.io/en/latest/config/), and [Flask-Limiter configuration](https://flask-limiter.readthedocs.io/en/stable/configuration.html).
