# Olumira

A caregiver-support platform for daily routines, visual communication, observations, and practical resources.

Olumira began with the observation that supporting someone with substantial support needs involves keeping track of routines, communication, activities, and small changes throughout the day. Its goal is to make that work calmer and more organized through accessible, human-centered software.

## What works today

- Dashboard with database-derived daily progress, completion counts, routine-group counts, and saved observations.
- Routine creation, editing, deletion, templates, and daily completion history.
- Visual communication choices and custom cards saved in the current browser.
- Saved observations with activity, date, notes, mood, and tags.
- Resource filtering and keyboard-accessible detail panels.
- Forest/sage design, original local garden illustration, responsive horizontal navigation, and mobile menu.

Days 15–16 add registration, sign-in/sign-out, verified-email access, password recovery, account settings, and revocable server-checked sessions. New accounts receive isolated data scopes; legacy visitor records remain preserved and unclaimed. Custom communication cards remain browser-local and account-namespaced. Family sharing and hosted production acceptance are not presented as complete.

**Local email testing sends no real email.** Verification/reset emails are queued encrypted and can be opened through the private `mail-preview` CLI. Production uses a scheduled TLS SMTP worker. Follow the [Day 16 setup and email runbook](docs/day-16-account-recovery.md) to test the full flow.

## Local setup

Use Python 3.14 (the version tested here), with a virtual environment:

```sh
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
mkdir -p database
```

For a **new, empty local database**:

```sh
venv/bin/python -m flask --app app db upgrade
venv/bin/python -m flask --app app run --port 5000
```

Open http://127.0.0.1:5000. No schema creation, data purging, or migrations happen automatically on startup. The current migration head is `0021`; register an account after migrating, verify its email, then sign in.

For an **existing pre-Day-13 SQLite database**, do not run the initial upgrade against its existing tables. Follow [baseline adoption](docs/database-migration.md) first. The original local database has not been stamped or migrated by this change; a verified recovery backup is in the ignored `database/backups/` directory.

## Configuration

Settings are read from environment variables when `create_app(config=None)` runs. `.env.example` documents them; `.env` is not automatically loaded. Export variables in your shell or configure them in your hosting dashboard. Never commit real connection strings or secrets.

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development` (local default), `testing`, or `production`. Render defaults to production. |
| `SECRET_KEY` | Stable random signing key. Required in production; development-only fallback retains local demo compatibility. |
| `DATABASE_URL` | PostgreSQL URL in production; optional SQLite SQLAlchemy URL locally. PostgreSQL URLs are normalized to the psycopg driver. |
| `APP_TIMEZONE` | Routine day boundaries and greetings; defaults to `America/Chicago`. |
| `RATELIMIT_STORAGE_URI` | Shared Redis connection in production; `memory://` for local development. |
| `AUTH_SESSION_SECONDS` / `AUTH_IDLE_SECONDS` | Absolute/idle limits, default 43200/1800 seconds. |
| `TRUSTED_PROXY_HOPS` / `TRUSTED_HOSTS` | Exact trusted proxy count and allowed production hostnames. See the Day 15 runbook. |
| `PUBLIC_APP_URL` | Canonical application origin; production requires HTTPS. Never derived from request Host. |
| `MAIL_BACKEND` / `MAIL_FROM` | Local development preview, or provider-verified SMTP sender in production. |
| `MAIL_ENCRYPTION_KEY` | Independent Fernet key for encrypted queued emails; required in production. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD` | Authenticated TLS SMTP configuration. Delivery requires the scheduled email worker. |
| `VERIFY_TOKEN_SECONDS`, `RESET_TOKEN_SECONDS`, `EMAIL_CHANGE_TOKEN_SECONDS` | Default 3600 / 1800 / 1800 seconds. |
| `TEST_POSTGRES_URL` | Opt-in integration test against a new, empty, disposable PostgreSQL database only. |

Development defaults to an absolute SQLite path at `database/olumira.db`. Tests create temporary databases and run real migrations. Production refuses missing/default/short secrets, non-PostgreSQL database URLs, or per-process memory throttling; disables debug/testing; and enforces secure session cookies and CSRF. Shared Redis is required for rate limiting. Configure TLS in `DATABASE_URL` as required by your PostgreSQL provider (for example `sslmode=require`); no TLS settings are silently disabled.

Generate a signing key locally without storing it in source:

```sh
venv/bin/python -c 'import secrets; print(secrets.token_hex(32))'
```

## Architecture

```text
app.py                         # gunicorn/Flask compatibility entry point
olumira/
  __init__.py                  # create_app, workspace hook, error handlers
  config.py                    # environment-aware configuration
  extensions.py                # unbound SQLAlchemy and Flask-Migrate
  models.py                    # legacy entities, users, revocable sessions
  forms.py                     # CSRF-protected account validation
  content.py                   # existing resource/communication catalog
  commands.py                  # explicit backup/adoption/transfer CLI
  mail_commands.py             # private previews and scheduled SMTP delivery
  routes/                      # dashboard, routines, communication,
                               # observations, resources, auth blueprints
services/                      # business operations, dashboard context,
                               # transactions, transfer validation
migrations/                    # version-controlled Alembic baseline
  versions/0001_legacy_schema.py
  versions/0002_user_authentication.py
  versions/0003_account_recovery.py
templates/emails/               # branded text/HTML transactional emails
templates/components/ui.html    # reusable semantic Jinja macros
templates/                     # existing pages and branded error page
static/                        # CSS, JavaScript, original SVG illustration
tests/                         # unit/integration and browser checks
docs/                          # checkpoints and migration runbook
```

Public URLs are unchanged. Internal endpoints now use names such as `dashboard.dashboard` and `routines.toggle_routine_completion`. All template links and form actions were updated. Database sessions are scoped to the Flask application context and removed on teardown; service writes commit together or roll back. Server error logs omit raw exceptions and submitted values to avoid exposing private content.

The baseline retains text dates, nullable legacy ownership, existing IDs, metadata, and the composite completion key. No ownership foreign keys were added to reinterpret historical records; new writes remain scoped through the existing visitor workspace mechanism. Completion foreign keys cascade on routine deletion. See the [database runbook](docs/database-migration.md) for constraints and transfer details.

## Tests and previews

```sh
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m pip check
venv/bin/gunicorn --check-config app:app
```

For rendered browser checks:

```sh
venv/bin/python -m pip install -r requirements-dev.txt
venv/bin/python -m playwright install chromium
venv/bin/python tests/browser/check_ui.py
venv/bin/python tests/browser/check_accounts.py
```

The browser script starts a temporary local server/database, exercises login/registration and all five protected pages at 1440, 1280, 1024, 768, 390, and 320px, and checks overflow, navigation, keyboard actions, sampled text contrast, focus, forms, communication persistence, resource filters, reduced motion, and no-JavaScript navigation. Current screenshots and JSON reports are written to ignored `artifacts/after-day16/` and `artifacts/day16-accounts/`. Earlier dashboard captures are in `artifacts/before-day14/` in this workspace. The browser server stops after testing.

The PostgreSQL integration test is skipped unless `TEST_POSTGRES_URL` is explicitly set. It refuses an existing schema, imports only synthetic data, and leaves the disposable database for inspection. It never drops tables. Do not point it at a shared or production database.

## Render / production

The existing start command remains:

```sh
gunicorn app:app
```

Build with `pip install -r requirements.txt`. Before deploying, configure a stable `SECRET_KEY`, `APP_ENV=production`, the intended PostgreSQL `DATABASE_URL`, shared Redis `RATELIMIT_STORAGE_URI`, a canonical HTTPS `PUBLIC_APP_URL`, independent `MAIL_ENCRYPTION_KEY`, and authenticated TLS SMTP settings. Schedule `flask --app app mail-send-pending --limit 20` every minute using the same database/key. Review trusted proxy/host settings before exposing the service. Run reviewed migrations in a controlled pre-deploy step: `flask --app app db upgrade`. For legacy data, follow the backup, empty-target import, verification, and recovery procedure in the [runbook](docs/database-migration.md).

**No hosted PostgreSQL connection, data transfer, push, or deployment was performed.** Production will intentionally refuse to start without the required environment settings. Keep the existing deployment running until the database and cutover are approved and verified.

## Verification and remaining work

[Day 16 recovery checkpoint](docs/day-16-account-recovery.md) records current behavior, private email previews, SMTP-worker setup, migrations, verification results, and deployment/recovery gates. The [Day 15 checkpoint](docs/day-15-authentication.md) is the historical authentication foundation. Historical [Days 12–14 checkpoints](docs/days-12-14.md) record actual test results, changed files, known limitations, and suggested milestone commit messages. Browser checks do not establish formal WCAG compliance; assistive-technology and broader browser testing remain necessary. Production credentials and a disposable PostgreSQL test instance are still required to verify the PostgreSQL path before deployment.

## Days 17–21: family workspaces and collaboration

Private workspaces now support multiple caregivers, personalized care profiles,
secure invitations, owner/caregiver/viewer permissions and immutable activity events.
Choose a workspace and optional profile using the horizontal context controls.
Workspace settings provide profile, invitation and membership management. Owners
cannot be removed/demoted; ownership transfer and workspace deletion are unavailable.

Read the [implementation and demo guide](docs/days-17-21.md) and
[workspace security review](docs/workspace-security-review.md) for the permission
matrix, migration/backup procedure, tests, operational gates and remaining findings.
Migration head is **0006**; migrate before running this application version. Existing
account-linked records receive private workspaces; unclaimed legacy records remain
quarantined. No production deployment or public caregiver onboarding was performed.

Use `venv/bin/python -m pytest tests -q` for automated checks and
`venv/bin/python tests/browser/check_workspaces.py` for a temporary fictional browser
demo. Email verification and invitations use private `.eml` previews in development;
actual inbox delivery requires SMTP configuration and the explicit outbox worker.

## Day 22: visual routine builder

The routine library now supports ordered steps, visual previews, keyboard/touch
ordering, starter sequences, search, duplication and reversible archive/restore.
Daily checklists remain separate from multi-step sequence previews. Scheduling and
guided execution are the next review stages, not enabled placeholders.

Day 22 introduced migration **0007**; the current head is **0013**. Back up and migrate before starting the new
application version. See the [Day 22 report](docs/day-22-routine-builder.md) for
history preservation, permissions, tests, deployment instructions and limitations.
Run `venv/bin/python tests/browser/check_routine_builder.py` for the fictional demo.


### Days 23–24: recurring schedules and guided routines

Open **Routines → Schedule** for daily/seven-day views, or open a routine to add a
one-time, daily, weekday or weekly schedule. IANA timezone handling is explicit.
**Start or resume guided routine** saves shared step progress, pause/resume and
caregiver attribution. **History & saved runs** retains frozen sequence snapshots.
Run `flask --app app db upgrade` with the project environment before restarting.
See [behavior, architecture, migrations, demo and deployment instructions](docs/day-23-24-routines.md)
and [verification evidence](docs/day-23-24-verification.md).


### Days 25–26: visual communication

**Communication** now contains shared, profile-scoped picture boards and a visual
caregiver editor. **Open board** launches a separate focused experience with large
original picture cards, a phrase strip and prominent Speak controls. Browser-native
speech uses local voices only; written communication remains available without it.
Saved phrases persist across authorized caregivers; active messages stay in page
memory. Existing browser custom choices remain under **Quick choices**.

Migrate to **0011** before restarting. No new dependency or environment variable.
Custom uploads stay disabled until durable private media storage is configured.
See [setup, privacy, speech compatibility and rollback](docs/day-25-26-communication.md)
and [verification](docs/day-25-26-verification.md). A disposable fictional preview
can be started with `venv/bin/python scripts/preview_routines.py --port 5054`.


### Days 27–28: personalized communication and shared care

Select a care profile, then use **Communication → Display & speech preferences**
and **Manage favorites**. **Open my communication** uses that profile’s saved
board/preferences across devices. **Care team** connects assigned responsibilities,
routine/observation references, recipient-specific handoffs and safe shared activity.
The dashboard shows real responsibilities and pending handoffs. Viewers remain read-only.

Migrate to **0013** before restarting. No new dependencies or environment variables.
See [behavior, privacy, setup, demo and rollback](docs/day-27-28.md) and
[verification](docs/day-27-28-verification.md). A disposable fictional preview is
available via `venv/bin/python scripts/preview_routines.py --port 5055`.

Days 29–32 add structured observations, the searchable timeline, scoped caregiver insights, and private PDF/CSV reports. See [implementation and operating notes](docs/day-29-32.md) and [actual verification results](docs/day-29-32-verification.md). Reports use real stored events and disclose unknown historical times and unavailable scheduled completion rates.

## Days 33–36: core completion → premium experience

| Day | Phase | Implemented |
| --- | --- | --- |
| 33 | Core product completion | Unified calendar, custom recurring events and in-app reminder preferences |
| 34 | Core product completion | Stored resource library, server search and personal bookmarks |
| 35 | Core product completion | Profile-aware dashboard, real metrics and personal preferences |
| 36 | **PREMIUM EXPERIENCE PHASE 1: GUIDED ONBOARDING** | Saved setup, first-use guidance and contextual product tour |

Migrate to **0018** and restart the process. No new dependencies or environment variables. See [milestone implementation and operation](docs/day-33-36.md) and [verification/readiness](docs/day-33-36-verification.md). Background reminder delivery remains deferred to Day 38. The fictional interactive preview can be started with `venv/bin/python scripts/preview_routines.py --port 5059`.


## Days 37–39: Premium settings, notifications and privacy

Account → Settings & personalization links the existing secure account, dashboard, communication, calendar, workspace and new privacy controls. Personal accessibility settings persist per user. Calendar default view, week start and 12/24-hour clock change presentation only. Light/English are the supported appearance/language; reduced effects, larger text, enhanced contrast and simplified decoration work independently of shared communication preferences.

Migration head **0021** adds personal preferences, notification storage/preferences, expiring download grants and access-closure metadata. Existing care records are preserved. No dependencies or environment variables were added.

Task assignments and handoffs create private in-app notifications in their business transactions. Schedule the following commands using the same database and stable application configuration as the web process:

```sh
venv/bin/python -m flask --app app process-reminders
venv/bin/python -m flask --app app privacy-maintenance
```

Run reminders approximately every minute and privacy maintenance daily. No in-process scheduler is started automatically. On Render, configure a supported scheduled job or external scheduler; a sleeping Free web service is not a reliable worker. The reminder processor is restart-safe, observes saved lead times/categories, and catches up over the preceding 24 hours. Email remains the existing account/invitation channel; reminder email and push are unavailable.

Privacy exports are authenticated, reauthenticated, CSRF-protected JSON with single-use five-minute download grants. Personal exports exclude shared care records; workspace exports require an owner and include all profiles in that workspace. Exports are bounded to 10,000 rows/8 MiB and generated in memory. Account deletion anonymizes identifying account fields and revokes all sessions and memberships, while shared history remains. Sole owners must add another owner or close the workspace first. Workspace closure revokes all access/invitations and records an operator-review request; **it does not physically erase shared history or backups**. No automatic physical purge is claimed.

See [implementation, retention, backup and deployment details](docs/day-37-39.md) and [verification evidence](docs/day-37-39-verification.md). Fictional interactive preview: `venv/bin/python scripts/preview_routines.py --port 5072`. Do not use fictional credentials for real accounts.

## Day 40 — Premium UI/UX transformation

Olumira now uses a shared Modern Care premium stylesheet, a redesigned dashboard composition, consistent surfaces/controls, responsive horizontal navigation and dropdowns, differentiated calendar events, refined journals/boards/settings, and native-form loading feedback. Existing business logic, authorization, communication preferences and data are preserved. No migration or new dependency is needed; schema head remains **0021**.

See [the Day 40 transformation and verification report](docs/day-40.md). Run `venv/bin/python tests/browser/check_premium_transformation.py` for the six-width feature matrix. A separate fictional preview can be started with `venv/bin/python scripts/preview_routines.py --port 5081`; template reload is enabled for this loopback-only preview so UI iteration does not require resetting its temporary data. The normal application remains on port 5000.

## Day 40.1 — Premium visual refinement

Content-first dashboard, calendar and journals; compact filters and library cards; accessible resource controls; balanced care tasks; grouped settings with unsaved-change feedback; and refined onboarding/tour navigation. Existing data and security behavior are preserved, with no schema or dependency changes. See [the refinement and verification report](docs/day-40-1.md). A fictional verified-account preview can be started with `venv/bin/python scripts/preview_routines.py --port 5090`.

## Day 40.2 — Final premium experience refinement

Slimmer secure context switching, clear Preferences / Account & security navigation, consistent current sections, refined dashboard/calendar controls and purposeful sparse care layouts. No schema or dependency changes. See [the Day 40.2 report](docs/day-40-2.md). Run `venv/bin/python tests/browser/check_navigation_refinement.py` for real native context-switching checks and `venv/bin/python tests/browser/check_premium_transformation.py --day-40-2` for the six-width matrix. Fictional preview: `venv/bin/python scripts/preview_routines.py --port 5092`.

## Days 41–42 — Verified quality and security baseline

Testing now defaults to an independent in-memory database, blocks the normal SQLite database, preserves CSRF and forbids live SMTP in pytest. Runtime requirements pin the security-fixed cryptography 50.0.2. Production enforces HTTPS and trusted hosts; access logs redact query/referrer values; valid new/duplicate registrations share a generic public response. Existing data/schema are unchanged (**0021**).

```sh
venv/bin/python -m pytest -q --cov --cov-report=json --cov-report=xml --cov-report=html
venv/bin/python scripts/check_coverage.py
venv/bin/python scripts/run_browser_quality.py
venv/bin/python scripts/scan_secrets.py --history
```

For live database evidence, provide two fresh disposable databases via `TEST_POSTGRES_URL` / `TEST_POSTGRES_SECURITY_URL`, or use `venv/bin/python scripts/run_postgres_quality.py --bin-dir /path/to/postgres/bin --full`. The runner creates private temporary databases, disables TCP, exercises synthetic dump/restore and stops the server afterward. Never point tests at production. CI defines isolated PostgreSQL, coverage/security gates and browser journeys; remote CI execution is not implied by its definition.

Operator-only commands (not run automatically): `flask --app app mail-retention` is a dry run; `--apply` scrubs expired encrypted email bodies while retaining metadata. Recovery containment requires `flask --app app security-revoke-access --confirm 'REVOKE ALL ACCESS ARTIFACTS'`; it revokes all old sessions/links/invitations/exports but does not replace a post-backup closure/membership-revocation ledger. No care-history or backup erasure is claimed.

Read [quality evidence](docs/day41-quality-report.md), [security/privacy review](docs/day42-security-review.md) and [real-data release gates](docs/real-data-readiness.md). **REAL-DATA READINESS PENDING**: hosting encryption, deployed TLS/Redis/mail, operational ownership, independent security/privacy/legal review and human release approval remain required. No automatic commits, pushes or deployments.

Day 43 infrastructure: [readiness and test evidence](docs/day43-production-readiness.md),
[manual Render release](docs/render-deployment.md), [environment inventory](docs/environment-variables.md),
[backup/recovery](docs/database-backup-recovery.md), [rollback](docs/deployment-rollback.md),
[operational alerts](docs/incident-response.md). No automatic deployment or real-data approval.
