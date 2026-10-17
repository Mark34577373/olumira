# Days 33–36 verification

October 17, 2026. All demonstrations use fictional data. No commit, push or deployment was performed. Per-day files, features, migration/dependency notes, security/accessibility checks, limitations, manual steps and commit suggestions are in [the milestone report](day-33-36.md).

## Executed checks

| Check | Actual result |
| --- | --- |
| Final full pytest regression | **181 passed, 1 skipped, 18 subtests passed**, 401.87 seconds |
| Earlier full regression | 179 passed, 1 skipped, 18 subtests passed; one outdated dashboard-heading assertion was corrected |
| Focused integration, migration and legacy persistence | 24 passed |
| Final calendar/dashboard/onboarding focused check | 11 passed |
| Final onboarding check including background email rendering | 5 passed |
| Background-email and updated scheduling/dashboard regression checks | 2 passed |
| `tests/browser/check_product_experience.py` | 7 grouped functional checks, 60 viewport/page combinations, no failures |
| Existing `tests/browser/check_ui.py` | 62 checks including 42 route/viewport combinations; no failures or JavaScript errors |
| Live final preview | Port 5059: verified login, 30 final viewport/page checks, compact month view, separate first-use account, keyboard start and saved resume passed |
| Sampled text/button contrast | 9 new pages, no failures after calendar button-color correction |
| PostgreSQL offline migration generation | SQL generated through 0018, including resource seed and scope/exemption guards; no live connection |
| SQLite populated migration fixture | Original rows/columns preserved, repeated upgrade harmless, ORM/schema parity and FK checks passed; cross-workspace DB writes rejected |
| Local database | 0018 (head); preserved original values across 32 existing tables; integrity and foreign keys passed |
| Bandit on new calendar/resource/setup/preference services/routes | No findings |
| Gunicorn configuration | Passed |
| Black on 19 new/rewritten Python files | Passed |
| `git diff --check` | Passed |

The PostgreSQL test is skipped without `TEST_POSTGRES_URL`; no live PostgreSQL/Render or production concurrency/load result is claimed.

## Verified workflows

- Calendar: real scheduled routine and dated task integration, four views, category/date navigation, custom event replay/edit/conflict/cancel/archive/restore, timezone/DST recurrence, saved reminders, profile/workspace isolation, viewer restrictions and CSRF.
- Resources: server search and literal-wildcard handling, categories, full details, published-only access, validated HTTPS source links, personal bookmark/remove, duplicate prevention, saved-resource isolation and CSRF.
- Dashboard: actual active-template/task/observation counts, authorized upcoming custom event, checklist-versus-guided-run distinction, observation note minimization, per-member preferences, explicit preferred profile, viewer read-only controls and bounded query count.
- Premium setup: new user/family/profile, real starter routine/board, save/resume, optional skips, completion, restart, stale/forged steps, foreign profile denial, replay prevention and atomic rollback when a shared creation service fails. A lost workspace-creation response can be retried without a second workspace or a wrong-context resume. Existing members are exempted without fabricated completion timestamps. Background email templates render outside an HTTP request.

The browser scenario registers a fictional user and verifies the actual encrypted-development-outbox token, signs in, creates Fictional Cedar Family/Fern, saves/resumes setup, creates real starters, queues an optional invitation through workspace settings, tours actual feature pages and finishes onboarding. It then creates a routine schedule, assigned task and custom event, views them together, saves reminder preferences, searches a resource, bookmarks it and returns to real dashboard data. An unrelated family receives 404 on the event and cannot inherit bookmarks. Native keyboard controls, reduced motion and 320/390/768/1024/1440 widths are exercised.

The legacy browser regression additionally covers registration/verification/login/logout, existing communication interactions, resource quick-read focus restoration, routine completion/persistence, sampled contrast, navigation and no-JavaScript access. Tests obtain CSRF from the lightweight account form instead of rendering the increasingly complex dashboard for every POST; actual CSRF enforcement remains enabled.

## Local database and running preview

Before migration the normal local server was stopped. Exclusive recovery backup:

`database/backups/pre-day33-36-20261017T203642Z.db`

The backup matched the source. Additive 0014 → 0018 preserved **every original row/column value across 32 pre-existing tables**. New resource/setup records live in new tables; existing private content/identifiers were not rewritten. SQLite integrity/FKs passed. Port 5000 was restarted with current code. Downgrades refuse unreviewed loss; recovery uses a reviewed matching backup/code plan.

Final interactive preview: **http://127.0.0.1:5059/auth/login**. The separate temporary DB/key/cookie namespace preserves the real database and older preview data. `preview@example.com` contains fictional family/calendar/routine/communication/care data. `welcome-preview@example.com` exercises saved first-use guidance. Both are verified through the real development verification service. Passwords are kept out of this repository in the owner's private temporary `olumira-preview-5059-access.json` file. Demo edits last until the process stops.

Screenshots are ignored under `artifacts/day33-36`. Desktop dashboard, compact mobile calendar and mobile setup were visually inspected. The final setup layout omits redundant global workspace/profile switchers; the guided step provides those choices with explicit saved context. No public demonstration route or real-family data was added.

## Remaining release gates and deliberate limits

- Background reminder email/push is deferred to Day 38. In-app reminders are computed on page load, not proactively delivered. Reminder attention windows and lead times are disclosed.
- Custom edits/status changes affect the whole series; no occurrence exceptions or drag rescheduling. Calendar is bounded to 42 days/3,000 occurrences; 500 custom series per profile. Canceled/archived custom series remain retrievable and restorable.
- The resource library contains general organizational guides, not clinical/expert or emergency guidance. Unknown publication/review dates stay unknown. Global administration remains code-managed; ordinary members cannot edit curated content.
- Dashboard checklist day uses APP_TIMEZONE; greeting, task-day count and analytics use the saved personal timezone. Current snapshot metrics do not reconstruct historical state. Existing unavailable scheduled-completion percentages remain unavailable.
- Setup saves completed steps, not unsaved keystrokes. Existing records are reused by choice; setup is optional for migrated members. Invitations follow the existing verified-account acceptance and mail-worker configuration.
- Actual SMTP inbox delivery, live PostgreSQL, hosted Render acceptance, production load/concurrency, formal screen-reader/WCAG certification and regulatory readiness remain unverified. No new external service was configured or deployed.

**OLUMIRA PREMIUM EXPERIENCE PHASE 1 — COMPLETION REPORT:** The local product now connects first-use guidance to real persisted family/profile setup and the working calendar, resource, dashboard, routine and communication features. Saved state, clear optional choices, safe retries, accessible native navigation and contextual guidance reduce setup friction without introducing a parallel application architecture. Production release remains subject to the gates above.
