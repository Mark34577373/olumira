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

Visitor workspaces use a signed cookie; this is not authentication. Custom communication cards remain browser-local. Losing cookies loses access to the visitor workspace. Accounts, family sharing, PostgreSQL hosting, and production security hardening are not presented as complete.

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
venv/bin/python -m flask --app app run --port 5050
```

Open http://127.0.0.1:5050. No schema creation, data purging, or migrations happen automatically on startup.

For an **existing pre-Day-13 SQLite database**, do not run the initial upgrade against its existing tables. Follow [baseline adoption](docs/database-migration.md) first. The original local database has not been stamped or migrated by this change; a verified recovery backup is in the ignored `database/backups/` directory.

## Configuration

Settings are read from environment variables when `create_app(config=None)` runs. `.env.example` documents them; `.env` is not automatically loaded. Export variables in your shell or configure them in your hosting dashboard. Never commit real connection strings or secrets.

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development` (local default), `testing`, or `production`. Render defaults to production. |
| `SECRET_KEY` | Stable random signing key. Required in production; development-only fallback retains local demo compatibility. |
| `DATABASE_URL` | PostgreSQL URL in production; optional SQLite SQLAlchemy URL locally. PostgreSQL URLs are normalized to the psycopg driver. |
| `APP_TIMEZONE` | Routine day boundaries and greetings; defaults to `America/Chicago`. |
| `TEST_POSTGRES_URL` | Opt-in integration test against a new, empty, disposable PostgreSQL database only. |

Development defaults to an absolute SQLite path at `database/olumira.db`. Tests create temporary databases and run real migrations. Production refuses missing/default secrets or a non-PostgreSQL URL, disables debug/testing, and uses secure session cookies. Configure TLS in `DATABASE_URL` as required by your PostgreSQL provider (for example `sslmode=require`); no TLS settings are silently disabled.

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
  models.py                    # legacy-compatible entities
  content.py                   # existing resource/communication catalog
  commands.py                  # explicit backup/adoption/transfer CLI
  routes/                      # dashboard, routines, communication,
                               # observations, resources blueprints
services/                      # business operations, dashboard context,
                               # transactions, transfer validation
migrations/                    # version-controlled Alembic baseline
  versions/0001_legacy_schema.py
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
```

The browser script starts a temporary local server/database, exercises all pages at 1440, 1280, 1024, 768, 390, and 320px, and checks overflow, navigation, keyboard actions, sampled text contrast, focus, forms, communication persistence, resource filters, reduced motion, and no-JavaScript navigation. Screenshots and JSON reports are written to ignored `artifacts/after-day14/`. Earlier dashboard captures are in `artifacts/before-day14/` in this workspace. The browser server stops after testing.

The PostgreSQL integration test is skipped unless `TEST_POSTGRES_URL` is explicitly set. It refuses an existing schema, imports only synthetic data, and leaves the disposable database for inspection. It never drops tables. Do not point it at a shared or production database.

## Render / production

The existing start command remains:

```sh
gunicorn app:app
```

Build with `pip install -r requirements.txt`. Before deploying, configure a stable `SECRET_KEY`, `APP_ENV=production`, and the intended PostgreSQL `DATABASE_URL`. Run reviewed migrations in a controlled pre-deploy step: `flask --app app db upgrade`. For legacy data, follow the backup, empty-target import, verification, and recovery procedure in the [runbook](docs/database-migration.md).

**No hosted PostgreSQL connection, data transfer, push, or deployment was performed.** Production will intentionally refuse to start without the required environment settings. Keep the existing deployment running until the database and cutover are approved and verified.

## Verification and remaining work

[Days 12–14 checkpoints](docs/days-12-14.md) record actual test results, changed files, known limitations, and suggested milestone commit messages. Browser checks do not establish formal WCAG compliance; assistive-technology and broader browser testing remain necessary. Production credentials and a disposable PostgreSQL test instance are still required to verify the PostgreSQL path before deployment.
