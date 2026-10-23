# Registration 500 investigation — 2026-10-22

Status: **hosted root cause not yet established; not claimed repaired**.

## Evidence

- Current isolated real-HTTPS browser registration passes at 375px and 1440px:
  native POST, correct fields, CSRF/session/referrer validation, hashed persisted
  fictional accounts and redirect to check-email.
- The supplied Render log is only `Request failed: status=500
  endpoint=auth.register`. Existing exception handlers deliberately suppress raw
  exception messages/SQL parameters. That line does not establish the exception
  class, failing function or database condition.
- The public hosted `/health/ready` independently returned
  `{"status":"unavailable"}`. This endpoint checks database connectivity, Alembic
  revision and shared Redis availability. It does not disclose which check failed.
  No live account records, environment secrets or Render private logs were accessed.
- The earlier 400 was reproduced as the no-referrer/HTTPS CSRF conflict and fixed
  separately. A 500 is a different failure path; no shared cause has been proven.
- No local PostgreSQL tools or disposable PostgreSQL URL are available here. A
  SQLite success is not a claim that production PostgreSQL/schema/permissions work.

## Pipeline reviewed

The native form posts display_name/email/password/confirm_password/csrf_token to
`auth.register`. Global transport and CSRF checks precede form validation; no
script serializes or drops its fields. `REGISTRATION_ENABLED=False` renders the
closed-registration explanation. There is no independent beta-invite signup gate;
workspace invitations do not bypass registration policy.

`register_user` validates, hashes using the existing scrypt settings, checks the
normalized unique email, and atomically creates owner, user, workspace, membership,
audit and starter routines/steps. Nested services share the outer transaction;
failures roll back, and duplicate races are checked after rollback. No transaction,
constraint, hashing or authorization logic was changed speculatively.

The registration route then requests a verification link using the encrypted
outbox. That request is caught/redacted on failure. SMTP is performed by the
separate delivery worker, not synchronously by signup. Registration does not log
the user in; successful permitted submissions redirect to `auth.check_email`.
All referenced endpoints exist. Session keys/production configuration could not
be independently inspected on Render.

## Changes made

- `olumira/privacy_logging.py`: a shared failure logger records request ID,
  endpoint, exception class, DBAPI class, validated five-character PostgreSQL
  SQLSTATE and application file/line/function stack. It never formats exception
  messages, SQL, parameters, trace source lines, locals or arbitrary DB details.
- `olumira/__init__.py`: both SQLAlchemy failures and Flask unhandled failures use
  that logger. Existing rollback, generic 500 page, security headers and CSRF
  remain. Complete raw production tracebacks remain suppressed because DBAPI
  exception strings can expose credentials and private records.
- `tests/test_registration_diagnostics.py`: simulated DBAPI UndefinedTable and
  unhandled RuntimeError verify class/location/request-ID diagnostics, SQLSTATE
  42P01, unchanged generic HTTP 500 and redaction. **These injected failures are
  diagnostic tests, not evidence that the hosted database has a missing table.**

No database models, migrations, production settings, account records or signup
logic were changed. No commit, push or deployment.

## Verification

```sh
venv/bin/python tests/browser/check_signup_https.py
venv/bin/python -m pytest -q tests/test_signup_https.py tests/test_authentication.py tests/test_infrastructure.py tests/test_security_hardening.py
venv/bin/python -m pytest -q tests/test_registration_diagnostics.py
```

Results: real-HTTPS browser mobile/desktop signup **passed**; **44 existing/focused
tests passed**; **2 diagnostic tests passed**. Both pytest runs emitted the existing
OpenSSL legacy-provider warning. `git diff --check` passed. External email,
production PostgreSQL and successful hosted signup remain unverified.

## Required evidence before a registration repair

A read-only Render Shell probe was requested from the operator: connect using the
configured app engine, SELECT 1, read only Alembic revision identifiers, and on
failure print exception/DBAPI classes and SQLSTATE without exception messages or
credentials. It performs no migration and creates no account.

Alternatively, after an operator-approved release of the diagnostic changes,
reproduce once with an approved fictional account and provide the `Request
exception` log with the matching request ID. It will identify the actual code line
and exception category safely. Do not enable DEBUG, log SQL parameters, reset the
production database, relax TLS, disable CSRF or run unreviewed migrations to guess
at a fix. If an existing complete traceback is available, review it privately and
redact credentials, SQL values, email addresses and tokens before sharing.

The actual minimal repair and its targeted regression must follow the observed
exception. Until then this task remains incomplete; the generic browser 500 page
and endpoint-only log cannot establish the failing line.
