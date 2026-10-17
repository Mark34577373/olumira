# Days 29–32 verification and readiness

Verified October 17, 2026 against fictional isolated test databases and the preserved local application database. No commit, push or deployment was performed. Implementation, per-day features/files/migrations/dependencies/accessibility/security/manual steps and suggested commit messages are documented in [the milestone report](day-29-32.md).

## Executed checks

| Check | Actual result |
| --- | --- |
| Full `venv/bin/python -m pytest -q` | **165 passed, 1 skipped, 18 subtests passed**, 364.14 seconds |
| PostgreSQL integration test | Skipped: `TEST_POSTGRES_URL` is not configured; no live PostgreSQL result is claimed |
| Final focused PDF/CSV/report suite after text-budget and escaping refinements | **5 passed**, 16.01 seconds |
| Focused journal/dashboard/interface check after final recent-entry integration | **11 passed, 5 subtests passed**, 20.56 seconds |
| Focused persistence/schedule migration/journal/report check after compatibility fixes | **18 passed**, 35.37 seconds |
| `tests/browser/check_journal_reports.py` | **6 grouped workflow checks, 30 viewport/page checks**, no failures |
| `tests/browser/check_ui.py` | **62 checks**, including 42 route/viewport combinations; no failures or JavaScript errors |
| Long-note PDF | Valid six-page PDF; accented Latin, Greek, Cyrillic and CJK content extracted; page-number assertions passed |
| PDF visual verification | PyMuPDF rendered all six pages; every page visually inspected; automated text bounds remained within document margins |
| Actual final preview | Verified sign-in, Fictional Fern journal, actual 1 completed guided routine/1 timed observation, successful PDF browser download, 390px layout without horizontal overflow |
| Main local server | `http://127.0.0.1:5000/auth/login` returned 200 |
| `venv/bin/gunicorn --check-config app:app` | Passed |
| `venv/bin/pip check` | No broken requirements |
| Bandit on journal, insights, reports, observation routes and privacy logging | Passed with no reported findings after using standard HTML escaping |
| Black check on ten new/rewritten Python files | Passed |
| `git diff --check` | Passed |
| Local `flask db current` | **0014 (head)** |
| PostgreSQL offline `flask db upgrade --sql` | Generated through 0014 with additive columns, indexes and reference/provenance guards; no live database connection |

## Coverage and concrete evidence

The new journal tests create an actual observation with category/tags and local clock time, verify UTC conversion, then edit it as another authorized caregiver. Original author and creation timestamp remain unchanged. A stale version gets 409. Archive removes it from the active timeline; Archived visibility finds it; Restore makes it active again. Invalid dates/DST gaps/timezones/references preserve entered text. Viewer mutation, CSRF omission, foreign workspace detail/edit and switched-profile detail access are denied.

Timeline tests create 23 same-time observations to verify descending ID tie-breaking and 20-record pagination. Combined category/tag/search/custom dates find the correct records. Literal percent search is escaped, rather than behaving as a SQL wildcard. Browser detail/edit/return preserves the active filters.

Analytics tests complete a real one-step guided routine using the existing session service and its completion event. The selected two-day series is exactly `[0, 1]`. Archiving its current template does not erase its completed frozen history. Observation archive changes the observation count without changing routine totals. Date-only entries are distinct from timed entries. DST bounds are exactly 23 and 25 hours on the relevant Chicago dates. Task completion repeated as the same desired state counts once. Actual handoff acknowledgment reduces the current pending count; that current count remains independent of selected historical dates.

Report tests generate a real PDF and parse its pages, then generate CSV with a fictional `=HYPERLINK(...)` note and verify its apostrophe prefix. Other leading whitespace/control/formula examples are neutralized. Selected sections exclude unrequested datasets. Invalid format, missing sections, unknown profile, CSRF omission, viewer access, over-limit row/text payloads and stale previews are rejected. Identical report/analytics configuration shares the same calculation service. An empty authorized profile does not receive another profile's observation.

The real browser scenario signs in, selects Fictional Fern, creates “Completed Morning Routine Independently,” assigns Achievements/morning/independent and a real completed run, filters the timeline, edits the description, checks insights, previews a report and downloads PDF/CSV. An authorized caregiver can see it; an unrelated workspace receives 404. Keyboard focus/Enter submission and 320/390/768/1024/1440 layouts are exercised. The pre-existing interface regression additionally verifies encrypted-development-inbox verification, login/logout, routines, communication, resources, sampled contrast, focus, reduced motion and no-JavaScript navigation.

The browser scripts' results are grouped functional checks, not assertions of formal WCAG certification. No SMTP delivery to a real mailbox, screen-reader certification, Safari/Firefox acceptance or hosted load test was performed.

## Actual local database preservation

The normal local web process was stopped before the upgrade. An exclusive private backup was created at:

`database/backups/pre-day29-32-20261017T200139Z.db`

The backup was compared with the source before migration. After additive `0013 → 0014`, **all original columns and all original row values across 32 pre-existing tables matched**, including observation IDs/date/notes/tags and related care/routine data. The comparison intentionally selects original columns, so added columns do not cause false differences. SQLite integrity and foreign-key checks passed. The normal server was restarted; later live login GET returned 200.

The automated populated migration fixture independently verifies legacy observation metadata remains unknown, the original category default/version are correct, repeated upgrades are harmless, and ORM/schema comparison has no drift. Legacy adoption validates only baseline indexes; the legacy-only transfer utility rejects rich observation metadata rather than silently dropping it.

The backup is ignored by Git and was not exposed through a static URL. No data reset, destructive downgrade or automatic migration-on-startup was introduced.

## Current interactive preview

The final fictional preview runs at **http://127.0.0.1:5057/auth/login**. Its temporary database, cookie namespace, signing key and fictional accounts are separate from port 5000 and older previews. Credentials are stored in the owner's private temporary `olumira-preview-5057-access.json` file; no password is committed here. The account has completed the real development email-verification token flow, so preview sign-in does not wait for an external email.

Select Fictional Fern, then Observations → Timeline → Insights → Reports. The seed uses genuine completed RoutineSession records and structured observations; chart counts are not hardcoded. Existing previews on earlier ports were left untouched. The final preview lasts until its process stops; changes made there are temporary.

Fictional screenshots and exports are ignored under `artifacts/day29-32`, including the six-page long-note PDF, browser PDF/CSV, desktop/mobile insight captures, and a final live-preview PDF. Generated user reports otherwise remain in memory until delivered to the authorized browser; no public persistent report store exists.

## Readiness and explicit limitations

The four milestones are functionally implemented and verified locally. Production release remains conditional on live PostgreSQL migration/concurrency tests, hosted Render smoke/load tests, trusted HTTPS/proxy settings, Redis, secure keys, operational backups/restore and actual SMTP configuration/worker delivery acceptance. This work did not deploy, configure external services or establish legal/clinical/regulatory compliance.

Known product limits are deliberate and disclosed:

- Scheduled completion percentage is **unavailable** because a reliable historical eligible/canceled-occurrence denominator is absent. The UI never substitutes launched sessions as that denominator.
- Legacy unknown authors/event times/creation times remain unknown. Date-only observation counts are shown separately from time-based trends.
- Private attachments remain deferred until durable authorized storage exists.
- Reports are limited to 366 inclusive days, 500 selected detail records and a 100,000-unit detail-text budget (line breaks weighted to bound pagination). Oversize exports fail without truncation.
- PDFs are not tagged for PDF/UA and do not provide complex-script shaping. Standard CJK fonts may depend on PDF viewer substitution. Unsupported glyphs are represented by code points; HTML and CSV alternatives retain original text.
- Snapshot metrics (active templates, pending handoffs and task statuses) describe current state, not reconstructed historical state. Reopened tasks are excluded from completed-task counts.
- Timeline offset pagination can shift when caregivers insert records concurrently. No heavyweight search engine or public report-sharing system is added.
- Local application logs suppress raw exceptions/submitted values and Werkzeug query values. Hosting/Gunicorn/proxy access-log query suppression must also be configured as described in the runbook.

Use [the implementation/runbook](day-29-32.md) for repeatable commands, manual checks and the four suggested milestone commit messages. Nothing was committed, pushed or deployed automatically.
