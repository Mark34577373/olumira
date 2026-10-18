# Day 41 — Automated quality and reliability evidence

Status: complete local quality baseline, with real-data release gates remaining. No commit, push or deployment.

## Audit and test foundation

Flask application factory, 14 blueprints, Jinja/native browser forms, SQLAlchemy, 43 tables and additive Alembic revisions through **0021**. The route inventory contains **100 registered rules**. Existing pytest/unittest fixtures already used disposable SQLite files, real CSRF, fictional verified users and membership/profile scopes. Existing browser scripts use Playwright with private temporary databases and an encrypted development mailbox. No new frontend framework.

Implemented:

- Testing defaults use an independent in-memory database and a fresh signing secret, ignore inherited production database/mail-key/public-origin settings, force an in-memory limiter and development mail, and refuse the normal application SQLite file (including resolved aliases).
- Autouse pytest SMTP guard forbids real SMTP constructors; transport-specific tests must mock them. CSRF remains enabled. No password-hash weakening or network-based fixture data.
- Coverage.py/pytest-cov with branch-aware JSON/XML/HTML and JUnit output; security/core gates in `scripts/check_coverage.py` (85% / 80%). The security scope includes authentication, recovery, membership, collaboration, privacy, mail/recovery services, app/config/forms/logging and all HTTP route modules; missing coverage files fail closed. Targets are not security certifications.
- Shared runner reuses nine existing real browser journeys, stores per-script exit codes and timing, preserves other results during focused retries, and fails on unresolved failures.
- New route-wide CSRF regression iterates every registered POST route, plus test-environment, Host/HTTPS/proxy/header/logging regressions and a full-schema synthetic backup/restore/containment test.
- New live PostgreSQL modern-tenant test checks private boards, calendar queries, forged context, membership revocation and two concurrent attempts to redeem one export grant. Existing PostgreSQL transfer/sequence test remains. Both refuse nonempty schemas.
- CI workflow uses read-only GitHub permissions, commit-pinned actions, isolated PostgreSQL service databases, branch coverage gates, static/dependency/secret scans and browser journeys. CI configuration exists; no remote CI run is claimed.

## Coverage map and authorization matrix

| Area | Existing/new evidence |
| --- | --- |
| Registration, login, hashes, cookies, expiry, rotation, revocation, enumeration-resistant login | `test_authentication.py`, `test_account_recovery.py`, `test_security_hardening.py` |
| Verification/reset/email-change lifetime, purpose and single use; encrypted queue/TLS mocks | `test_account_recovery.py` |
| Family/profile isolation; invitations, role changes/removal, pending invite denial; CSRF | `test_workspaces.py`, `test_navigation_refinement.py`, route-wide security regression |
| Routine builder, reorder/duplicate/archive; recurrence/DST; launch/completion idempotency and concurrency | `test_routine_builder.py`, `test_routine_scheduling_sessions.py` |
| Board/card/phrase/favorite/preference scope and permission boundaries | `test_communication.py`, `test_personalization.py` |
| Journal search/category/tag/author/date/archive/pagination; XSS escaping and stale updates | `test_journal.py` |
| Calculated insights, date boundaries, scoped PDF/CSV, formula protection, empty/large export bounds | `test_insights_reports.py` |
| Event recurrence/DST, reminder preferences, idempotent reminder retries, authorization | `test_calendar.py`, `test_notifications.py` |
| Tasks, handoffs, recipients/acknowledgment, revoked members, role/scope checks | `test_care_coordination.py` |
| Personal/workspace exports, single use/expiry/limits/role rechecks; closure/anonymization and retained history | `test_privacy.py` |
| Fresh/repeatable/historical migrations, constraints, orphans, rollback, no model drift | `test_persistence.py` and feature migration suites |
| Full-schema synthetic restoration and explicit recovery revocation | `test_recovery_integrity.py` |
| Published resources and per-user bookmarks | `test_resources.py` (resources are shared product guides, not private family uploads) |
| Onboarding, dashboard/user preferences and saved-step/version isolation | `test_onboarding.py`, `test_dashboard_personalization.py`, `test_personal_settings.py` |

Actual roles come from `services.workspaces.PERMISSIONS`:

| Capability | Owner | Caregiver | Viewer |
| --- | --- | --- | --- |
| Read authorized workspace/profile records | Yes | Yes | Yes |
| Create/edit/archive routines, boards/phrases, observations, events; complete routines | Yes | Yes | No |
| Manage tasks/handoffs and acknowledge recipient handoffs | Yes | Yes | No |
| Generate scoped PDF/CSV reports | Yes | Yes | No |
| Invite/remove members, change roles, manage/close workspace, workspace JSON export | Yes | No | No |
| Personal settings/account details and personal JSON export | Own account | Own account | Own account |
| Delete/anonymize own account | Password + confirmation + sole-owner constraint | Same | Same |
| Physically erase shared history/backups via application | No such capability | No such capability | No such capability |

Personal export is not permission to export shared care records. Workspace JSON exports require an owner and deliberately include all workspace profiles, with explicit explanation. Exact-profile feature views exclude workspace-wide/null-profile rows unless that context is selected. Account settings remain available independently of membership.

## Commands and evidence

Primary commands:

```sh
venv/bin/python -m pytest -q --cov --cov-report=json --cov-report=xml --cov-report=html --junitxml=artifacts/day41-42/pytest.xml
venv/bin/python scripts/check_coverage.py
venv/bin/python scripts/run_browser_quality.py
venv/bin/python scripts/scan_secrets.py --history
venv/bin/bandit -r olumira services scripts -ll -f json -o artifacts/day41-42/bandit-final.json
venv/bin/pip-audit -r requirements-dev.txt --format json --output artifacts/day41-42/pip-audit-dev.json
```

Final complete run (PostgreSQL enabled): **212 passed, 29 subtests passed, 0 failed, 0 skipped, 0 warnings**, **517.43 seconds**. Collection: **212 tests**. JUnit reports 241 cases because it includes the 29 successful subtests; these are not counted as 241 independent primary tests.

Final combined statement/branch coverage: **88.80%** overall; statement coverage **91.77%**, branch-only **78.75%**. Security-scope combined coverage **90.82%** (gate 85%); core service combined coverage **87.57%** (gate 80%). Both gates passed. Synthetic gate tests also confirmed rejection of zero coverage and a missing authentication module.

| Relevant module | Combined coverage |
| --- | ---: |
| `services/authentication.py` | 91.25% |
| `services/account_recovery.py` | 87.98% |
| `services/workspaces.py` | 95.56% |
| `services/collaboration.py` | 88.97% |
| `services/privacy.py` | 89.10% |
| `services/email_delivery.py` | 92.79% |
| `olumira/config.py` | 87.88% |
| `olumira/privacy_logging.py` | 93.65% |

The legacy `services/observations.py` compatibility helper is the lowest service at 43.2%; the primary scoped journal service is 85.4%. Coverage gaps are recorded, not hidden or filled with superficial tests. Core thresholds are aggregate targets, not a claim of complete branch coverage for each module.

Live PostgreSQL **17.11**: both opt-in tests passed, including two concurrent downloads yielding exactly one 200 and one 404. A third empty DB restored a synthetic `pg_dump` archive with schema head **0021**, **1 board** and **2 users** matching the source; restore exited successfully. The cluster used a private Unix socket with TCP disabled and was stopped in `finally`. It was compiled in a private temporary directory after packaged binaries were unavailable; source archive checksum was verified. TLS, hosted privileges and production recovery objectives were not tested.

Exact final complete command used the committed-source runner with the temporary PostgreSQL binary directory:

```sh
venv/bin/python scripts/run_postgres_quality.py --bin-dir /path/to/private/postgres/bin --full
venv/bin/python scripts/check_coverage.py
venv/bin/python -m coverage html
```

After rebuilding cryptography against **OpenSSL 3.6.5**, the architecture/authentication/recovery/privacy/mail-retention/security subset was rerun: **60 passed in 120.32 seconds**. Both PostgreSQL cases were then rerun on the rebuilt runtime: **2 passed in 9.77 seconds**, with another successful logical restore. `patched-native-focused.xml`, `postgres.xml` and `runtime.json` retain the evidence. The full 212-test run used cryptography 50.0.2 with the earlier 3.6.3 native build; it was not repeated in full after the native-only rebuild. Focused tests cover the affected encryption/authentication/export paths. This distinction is intentional, not an inferred full-suite result.

The initial full run was **208 passed, 2 skipped, 29 subtests passed**, 568.59 seconds, with 8 ResourceWarnings from undisposed auxiliary test engines. Those warnings were investigated; the autouse engine-pool cleanup fixture was added. The complete final run includes subsequent registration and mail-retention tests, enables PostgreSQL, and has no warnings/skips. It supersedes the initial results without concealing them.

Focused baseline after test isolation/transport changes: **45 passed** across architecture/authentication/account recovery. New security/recovery regressions: **6 passed**. Mail-retention regression: **1 passed**. Broad browser result after two focused corrections: **9/9 scripts passed**. New-family/invitation journeys were rerun after the generic registration fix. The matrix includes **252 checks** at 320/390/768/1024/1280/1440 px; navigation adds **42 viewport visits**, alongside real routine/board/task/handoff/report/privacy flows. Initial failures and retry results remain in `artifacts/day41-42/browser/`.

The two older browser scripts attempted to fill/click a collapsed observation composer. They now use the visible Add observation link; assertions and workflows were retained. No failing test was disabled. The new Host test exposed an actual 500 on rejected Host headers; remediation is documented in Day 42.

Artifacts include `pytest.xml`, `coverage.json`, `coverage.xml`, `htmlcov/`, browser logs/report, route/table/permission inventory and scans under `artifacts/day41-42/` (gitignored, fictional data only). CI evidence retention is seven days. Screenshots and sampled contrast/keyboard/focus/reduced-motion checks are not a complete accessibility audit.

## Repeating safely

Install `requirements-dev.txt`; install Playwright Chromium. Intel macOS no longer receives cryptography 50 wheels. This environment first built 50.0.2 using a vendored dependency, then inspected the native version and found it linked older OpenSSL 3.6.3. A checksum-verified OpenSSL 3.6.5 build was created in a private temporary prefix and the crypto package was rebuilt against it. Verify native versions rather than assuming a patched Python version guarantees patched native libraries.

```sh
OPENSSL_DIR=/path/to/reviewed/openssl-3.6.5 OPENSSL_STATIC=1 \
  venv/bin/python -m pip install --force-reinstall --no-deps --no-binary=cryptography --no-cache-dir cryptography==50.0.2
```

Do not reuse an older cached source wheel. The `openssl/vendored` feature alone is **not** the final patched native build used for verification here.

Use vendor-supported Linux/ARM macOS wheels where available. Do not downgrade crypto to make installation easier. Preserve the independent mail key across deployments; the dependency update does not rotate keys.

The reusable `scripts/run_postgres_quality.py` creates fresh private socket-only databases from supplied PostgreSQL binaries, runs tests plus logical dump/restore, and always stops its server. Direct opt-in live PostgreSQL tests require **two new, empty, disposable databases**, supplied as `TEST_POSTGRES_URL` and `TEST_POSTGRES_SECURITY_URL`; never use production or an existing schema. Tests keep the databases for inspection and do not drop them. With no URLs these tests are explicitly skipped, not silently treated as passing. CI provisions both databases. Synthetic SQLite restore evidence does not prove production backup encryption, recovery objectives or safe replay of later deletion/revocation requests.

Time-sensitive expiry, recurrence/DST, retention and retry tests use fixed dates/injected clocks or explicit `now` arguments where required; UI date presentation also has real-current-date tests. No global frozen time or reduced password hashing hides expiry or session behavior. There is no real SMTP/inbox delivery claim.

## Release scope

Day 41 establishes reproducible local evidence and a CI definition. It does not authorize sensitive real-family collection. See [Day 42](day42-security-review.md) and [real-data gates](real-data-readiness.md).

Suggested commit: `test: complete Olumira day 41 automated quality assurance`
