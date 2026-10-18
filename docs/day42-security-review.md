# Day 42 — Security and privacy review

Assessment date: **2026-10-18**, America/Chicago. Assessment covers this repository and isolated synthetic tests. **REAL-DATA READINESS PENDING**. No compliance certification, production assessment or autonomous release approval.

## Method and boundaries

Reviewed actual config, app hooks, auth/recovery/session helpers, centralized membership/profile scope, route mutation gates, scoped record queries, reports/exports, privacy/notification workers, additive schema/constraints and local access logs. Reused positive and attack-oriented tests across roles/families. Inventory: 100 registered rules, 43 tables, three roles; metadata-only artifact `artifacts/day41-42/application-inventory.json`.

Engineering references: [OWASP ASVS](https://github.com/OWASP/ASVS), [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), and [NIST Privacy Framework](https://www.nist.gov/privacy-framework/privacy-framework). These inform the review, not an assertion of conformance.

## Threat model

| Asset / boundary / actor | Credible threat | Existing or verified mitigation | Residual / next gate |
| --- | --- | --- | --- |
| Browser → Flask; unauthenticated visitor | Brute force, CSRF, token replay, unsafe redirects | scrypt passphrases, account/IP limits, real CSRF, exact redirect allowlist, expiring purpose-bound single-use hashed tokens | Shared Redis and abuse monitoring must be exercised on deployed topology |
| Browser session; compromised/stolen account | Cookie replay, stale roles after removal/reset | HTTP-only/Lax/production Secure host cookie; server session hashes, idle/absolute expiry and auth generations; membership reread each request | MFA/recovery/operator access policy and already-downloaded files remain outside these controls |
| Flask → DB; malicious family member | Cross-family/profile IDs, privilege escalation, foreign links in forms | Membership + capability helpers, exact scope, scoped related-record lookups, version/context checks and transactions | Independent adversarial review and deployed DB least privilege |
| Exports and downloads | Foreign records, stale grants, CSV formulas, memory exhaustion | Reauthentication, CSRF POST grants, user/workspace/scope/role rechecks, single use/expiry/limits; escaped CSV, in-memory PDF/JSON | Authorized recipients can retain downloaded copies; no remote revocation of files |
| Flask → email provider | Reset-link disclosure, SMTP failures leaking data | Fernet outbox, canonical origin and fragment links, TLS SMTP, generic recovery, redacted failures; expired-body retention command | Provider contracts, actual delivery/TLS config, worker schedule and mail-key rotation drill |
| Notifications / caregivers | Unauthorized recipient/content, retry duplicates | Membership/profile validation, private recipient inbox, deduplication, scoped link opening and viewer restrictions | Lock-screen/device policy; only in-app reminders implemented |
| Infrastructure operator → DB/backups | Full private-record exposure or secret compromise | Secrets external in production, hidden SQL parameters, access-artifact containment command | At-rest encryption, access reviews, logging, backup key separation and independent review unverified |
| Restored DB → app | Resurrect removed users, closed workspaces, grants or sessions | Synthetic restoration test and operator containment command | Must replay external deletion/member-revocation ledger before reopening; backups alone cannot establish latest revocations |
| Public demo → private data | Demo accounts or resets entering real tenancy | Loopback preview creates private temp DB and random credentials, explicitly ignores production DB URL | Public demo must be a distinct deployment/DB/key/worker set; no deployment was performed |
| Dependencies / CI | Vulnerable package or supply-chain compromise | Pinned Python requirements, advisory scan, commit-pinned actions, read-only workflow, local secret scan | Repeat scans, review upstream updates, runner access and SBOM/build provenance |
| Free-form care input → templates/reports | Stored XSS, SQL/formula injection, malformed dates/large payloads | Autoescaped Jinja, parameterized values, reviewed identifier allowlists, schema/service validation and request/export bounds | Rich HTML/uploads not supported; no generic URL fetch or unsafe deserialization found in reviewed code |

## Sensitive-data inventory and lifecycle

All DB and backup groups below require operator-managed at-rest encryption; this review does not assert it exists. Shared care history has **no automatic hard-delete TTL**. Closing workspaces revokes access but retains history. Account closure anonymizes identifying account fields and revokes access, while authorship IDs/shared records remain. Do not describe this as erasure of every copy. Corrections use existing authorized editors; immutable snapshots/audits preserve history.

| Classification / tables | Source and purpose | Access/export | Retention/deletion / recipients |
| --- | --- | --- | --- |
| Personal + credential secrets: `users`, `auth_sessions`, `account_tokens` | Account identity, password hashes, session/token digests and times | Account owner/security services; personal export includes account identity, excludes credentials/session/token material | Expiry/revocation is not row erasure. Account identity anonymized on closure. Never shared in workspace export or telemetry |
| Sensitive encrypted transport: `email_outbox` | Account/invitation recipients, raw links and bodies inside Fernet ciphertext | Mail worker/private development preview; excluded from JSON/report exports | `mail-retention` dry run / `--apply` scrubs bodies only after job expiry, retains delivery metadata. SMTP provider receives addressed message. Backups may retain earlier bodies |
| Personal relationships: `family_workspaces`, `workspace_memberships`, `workspace_invitations`, legacy `owners` | Workspace name, memberships/roles, invitation target/hash/expiry | Authorized members see permitted membership data; invitation issuance/role management owner-only | Closed workspace access revoked; invitations revoked on closure. Invite delivery goes to configured SMTP provider. No automatic physical history purge |
| Sensitive: `care_profiles` | Optional recipient name, preferences, interests, support notes | Authorized selected workspace/profile; owner workspace export | Shared retained history. Free-form fields can contain sensitive information; collect only necessary support detail, avoid unnecessary diagnosis/identity data |
| Sensitive routine history: `routines`, `routine_steps`, `routine_completions`, `routine_completion_snapshots`, `routine_schedules`, `routine_schedule_revisions`, `routine_occurrences`, `routine_sessions`, `routine_session_steps`, `routine_session_events`, `routine_launch_requests` | Templates, timing, step state and immutable history | Scoped members, writing/completion role checks, reports and owner workspace export | Archive/pause/end preserves historical records; no external analytics recipient |
| Sensitive communication: `communication_boards`, `communication_cards`, `saved_communication_phrases`, `communication_preferences`, `favorite_communication_cards`, `favorite_communication_phrases` | Explicit saved content and recipient presentation preferences | Scoped family/profile; viewer can communicate without managing; owner shared export | Live phrase composition stays page-local until explicitly saved. Browser local voices requested; OS/browser speech implementation remains a device/vendor review issue |
| Sensitive journal: `observations` | Free-form moments, categories/tags, linked care records, author/time | Scoped members, reports, owner shared export; personal export excludes shared journal | Archive/correct retains history. Search values already appear in browser URLs; use private devices. App access logging strips query values |
| Sensitive collaboration: `caregiver_tasks`, `caregiver_handoffs`, `handoff_recipients`, `handoff_tasks` | Assignments, handoff text/links and acknowledgment | Scoped family/profile; writers/recipients checked; owner shared export | Retained care history. Notifications are private in-app; no reminder email/push transport |
| Sensitive schedule: `calendar_events`, `reminder_preferences` | Event details/recurrence/times and per-user/profile reminder settings | Scoped views; private preference editing; shared events in workspace export, own preferences in personal export | Cancel/archive retains events. Processor must be scheduled; retries deduplicate |
| Public product guides + personal choices: `resources`, `resource_bookmarks` | Product-authored guides and own saved-resource IDs | Published guides; bookmarks user-specific and personal export | No private uploaded resource files. Personal bookmark rows removed on account closure |
| Personal preferences: `dashboard_preferences`, `onboarding_states`, `user_preferences`, `notification_preferences` | Own setup/defaults/accessibility/categories/retention | Current user, keyed by user/workspace where applicable; personal export | Personal rows removed on account closure; shared profile preferences remain separate |
| Sensitive inbox: `notifications` | Minimal category/title/entity metadata, user/workspace/profile recipient | Recipient only; role/link authorization rechecked; personal export | Read/dismissed rows after 30/90/180-day preference; unread retained. Maintenance command must actually run |
| Internal sensitive accountability: `audit_events`, `data_exports`, `deletion_requests` | Internal actor/target IDs, events, hashed download grants, closure requests | Owners where authorized; append-only audits; downloads authenticated and rechecked | Grants five minutes, single use, cleanup expires them. Audit/deletion metadata retained; DB triggers prevent ordinary audit edits/deletes. Operator access/retention policy still required |

No third-party trackers, analytics uploads, external image dependencies or server-side user URL-fetch feature were found in the reviewed application. HTTP browser access, hosted DB/Redis, SMTP and hosting operators still process relevant metadata/data. No attachment/upload feature is implemented; user-provided filenames/MIME/malware scanning are **not applicable now**, and must be reviewed before uploads are added.

## Findings and verified remediation

| ID / severity | Evidence and impact | Remediation / verification |
| --- | --- | --- |
| QA-01 Medium | Testing without an explicit DB inherited the normal local SQLite path; inherited limiter configuration could touch external Redis | In-memory default, production-environment isolation and refusal of normal DB path; `test_testing_defaults_cannot_reuse_normal_database_or_external_services` |
| SEC-01 Medium | Production set secure cookies/HSTS but did not enforce HTTPS before account requests | Canonical HTTPS redirect for safe methods and rejection of insecure mutations before CSRF/body parsing; trusted-proxy test verifies forwarded proto ignored without explicit hops |
| SEC-02 Low | Enabling trusted-host rejection exposed a 500 because rejected requests have no URL adapter and the error template called `url_for` | Minimal non-reflecting 400 for `SecurityError`; positive/negative Host regression passes |
| SEC-03 Medium | Query redaction covered Werkzeug only; Gunicorn's default request/referrer atoms could retain private searches | Gunicorn access dictionary/referrer redaction plus opt-in minimal `gunicorn.conf.py`; fixed-code security event logging without input payloads; formatter/duplicate-filter regressions |
| PRIV-01 Medium | Expired encrypted email bodies retained raw-link/recipient content unnecessarily | Explicit dry-run-first expiry scrub; deterministic active/expired/idempotency test. No automatic production execution, no care-history deletion or backup-purge claim |
| DEP-01 Supply-chain risk | Initial audit reported six entries representing **three distinct** cryptography advisories: CVE-2026-69247/69248/69249 | Pinned and installed **50.0.2**, local source build verified; runtime and dev advisory rescans zero known vulnerabilities (**76 runtime/QA dependencies** in the full requirements scan). Relevant upstream affected APIs are PKCS7/X.509 verification, not Olumira's Fernet path; no direct app exploit was demonstrated |
| REC-01 Medium operational gap | Old backup can restore live access artifacts that were subsequently revoked | Explicit, confirmed `security-revoke-access` command + synthetic full-schema restore test. External closure/revocation ledger and operator drill remain required |
| REG-01 Medium | Valid registration returned a distinct duplicate-email response, disclosing service membership within rate limits | New/duplicate valid registrations now share the same public redirect/message, no duplicate email is sent, and valid attempts hash before the existence check. Regression verifies equal public responses, no login or duplicate data/mail. No constant-time claim |

No verified critical or high-severity exploitable application issue remains identified by these local checks. This is not proof that none exists; independent review remains required. Initial Bandit output: 12 heuristics (4 medium SQL-string constructions, 8 low literal/assert heuristics). The four SQL identifiers are fixed model/constant allowlists, not request values; reviewed, narrowly annotated with rationale, not blanket suppressed. Low literals are algorithm names, token-setting names, subjects, rate-limit strings and the development-only key (rejected in production), plus preview asserts. Final Bandit medium/high gate: **0 reported findings**, with reviewed SQL identifier/tooling annotations; low heuristic findings remain explicitly triaged. Tooling subprocesses use selected local scripts/git argv and no shell.

Dependency details: [upstream security fixes](https://cryptography.io/en/latest/changelog/), [supported builds](https://cryptography.io/en/latest/installation/). Intel macOS prebuilt wheels are no longer published; a successful vendored-OpenSSL build was used here. Failed package/source attempts are retained as build logs and are not counted as a successful update. No custom cryptographic algorithm or field-encryption scheme was introduced.

### Native-library scope

Python advisory scans do **not** cover every native library. The initial local cryptography source build linked OpenSSL 3.6.3; upstream now publishes fixes in 3.6.5. Cryptography was subsequently rebuilt against a checksum-verified **OpenSSL 3.6.5** temporary-library prefix; `runtime.json` records the actually imported versions. After the rebuild, **60 focused tests and both live PostgreSQL tests passed**; the full-suite/native-runtime distinction is recorded in the quality report. The local Python framework's own `ssl` module reports **OpenSSL 3.5.7**, also older than upstream 3.5.9 fixes. This task does not replace system Python or OS libraries. Before real SMTP/hosted use, upgrade to a maintained provider/base runtime and review its complete native-library advisories/SBOM; this remains a **real-data release blocker**, not something a clean pip-audit result resolves. See [upstream native advisories](https://openssl-library.org/news/vulnerabilities/index.html). No direct Fernet exploit was demonstrated; affected native features and production reachability require separate assessment.

## Authentication, session and authorization assessment

Implemented and tested: long passphrases, scrypt hashing/upgrades, duplicate registration constraint/rollback, per-IP and account limits, revocable hashed sessions, login rotation, idle/absolute expiry, auth-generation changes, current-password reauthentication, expiring purpose-bound single-use recovery/verification/change links, canonical fragment URLs, safe redirect allowlist, production Secure/HttpOnly/Lax `__Host-` cookie and CSRF. Password/email changes revoke sessions according to existing policy. Actual SMTP delivery and Redis-backed distributed throttling are not locally established by memory/TLS-mock tests.

Membership/profile context is a selector, not authority. Helpers reread live membership/capabilities and scoped queries. Services validate related record workspace/profile; viewer management is denied server-side. Pending invites do not grant access, removal/role changes affect subsequent requests, and download grants recheck membership/role/identity/scope. Previously downloaded files cannot be revoked. UI button visibility is not the security boundary.

## HTTP / deployment / encryption

Implemented: HTTPS enforcement, default production host allowlist derived from canonical origin, explicit proxy-hop policy, secure cookie settings, no-store private pages/exports, sanitized errors, frame denial, no-referrer, nosniff, permissions policy, CSP with self-only scripts/object denial, bounded normal/builder request sizes. CSP retains inline **styles** for existing progress/presentation; it does not allow inline scripts. Local HTTP development remains functional.

Production must set independent random signing/mail keys, PostgreSQL URL, shared Redis, verified SMTP and HTTPS origin. Actual ingress topology, TLS certificates, DB/Redis TLS, at-rest encryption, snapshot encryption and operator privileges are **not verified**. HSTS/config tests alone do not demonstrate deployed HTTPS. DB private fields are plaintext at application level except the encrypted mail queue and hashed auth/grant values; do not claim end-to-end encryption. Field encryption would need search/report compatibility plus key recovery/rotation design, and was not improvised here.

## Logging, secrets and operations

Security events use fixed codes and validated internal IDs only. Existing immutable workspace audits cover membership/invitation/care/privacy changes. New auth event logs cover success/failure/logout and credential/session changes without emails/passwords/tokens. Logs are not a monitored audit service merely because code emits them. Day 43 must centralize restricted logs, set retention, detect spikes/failures, and identify operator actions. Use the supplied Gunicorn config; reverse-proxy/provider logs must independently omit queries, bodies, auth/cookies and private referrers.

Local scan found **0 high-confidence-pattern matches** in **264 working files / 482 reachable history blobs** at its execution point. This is a constrained pattern scan, not a guarantee that arbitrary passwords, unreachable objects, other branches/remotes or provider secrets are absent. No values were printed. Repeat at release; externally exposed secrets must be rotated, not merely deleted from Git.

See [Day 41 evidence](day41-quality-report.md) for exact executed commands/counts/coverage. Final complete suite: **212 passed, 29 subtests passed, 0 failures/skips/warnings**; security/core combined coverage **90.82% / 87.57%**. All nine representative browser scripts passed after focused corrections; the new-family/invitation journeys were rerun successfully after the registration change. Live PostgreSQL and synthetic dump/restore passed. No external production access, destructive tests or private-data upload was performed.

## Recovery, incident response and Day 43 handoff

1. Keep traffic/SMTP/reminder/maintenance workers stopped during recovery; restore to a separate private environment and verify integrity/schema.
2. Compare against independently retained account-closure, workspace-closure, member-removal and privacy-request records created after the backup. Reapply them **before** access opens. Do not silently resurrect revoked people or closed data.
3. Run `flask --app app security-revoke-access --confirm 'REVOKE ALL ACCESS ARTIFACTS'` against the reviewed restore only. It advances auth generations and revokes existing sessions, account tokens, invitations, download grants and unsent mail; it does not remove care history or replace the revocation ledger.
4. Rotate compromised signing/mail/provider/DB credentials using a reviewed recovery plan; preserve old mail keys only for approved recovery/rotation periods. Test decryptability before losing keys. Keys/backups must be separately protected.
5. Validate memberships, synthetic authorization tests, backup freshness, workers and alerts before a human reopening decision.

Preliminary incidents (procedures documented, **not operationally staffed/monitored**):

| Scenario | Detection / containment | Investigation / recovery / escalation |
| --- | --- | --- |
| Compromised account/session | Login alerts/user report; revoke account/all access artifacts as scope requires, remove suspect membership | Preserve minimal logs; review access/export/member changes; reset credentials, restore authorized roles; operator + privacy lead assess exposure |
| Suspected cross-family exposure | Authorization alerts/report; isolate affected routes/traffic and preserve evidence | Identify records/recipients/time window, independent security review, verified fix, affected-person notification decision with counsel |
| DB compromise/exposed deployment secrets | Provider/access anomaly; restrict ingress/workers and revoke/rotate exposed credentials | Preserve protected snapshot/logs, review DB/admin access and keys, rebuild trusted deployment, assess backup exposure and notifications |
| Accidental deletion/failed restore | Integrity/backup checks; halt writes and retain source/restore copies | Restore separately, compare counts/schema, replay privacy/revocation ledger, revoke restored artifacts, validate before reopen; escalate if recovery objectives missed |
| Outage/worker failure | Availability/queue-lag alerts (Day 43); stop unsafe retries, preserve DB | Diagnose isolated cause, restart idempotent jobs after validation, communicate scope/status; human rollback decision |
| Vulnerable dependency | Advisory CI/monitor alert; assess reachable APIs, isolate feature or pause release if severe | Patch/rebuild, rerun targeted/full tests and scans, review historical exploit evidence; operator/security/privacy leads decide notices |

For every incident record timeline, evidence access, affected scope, decisions, containment/recovery validation, owner and follow-up. A qualified human determines legal notification duties/timing; the application does not decide this autonomously.

## External privacy/legal review

Require qualified review of actual users, ages, countries/states, business relationships, care data, vendors and marketing before public real-data use. Checklist: U.S. state consumer/privacy/health-data rules, children's privacy and parental authorization, HIPAA covered-entity/business-associate applicability, consumer protection representations, privacy notice/terms, consent, DPAs/vendor contracts/subprocessors, retention/deletion/backup policy and incident-notification duties.

No legal determination is made. [HHS describes covered entities/business associates](https://www.hhs.gov/hipaa/for-professionals/covered-entities/index.html), and [FTC's COPPA guidance](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions) addresses covered child-directed/knowledge scenarios. These references are review inputs, not badges or an applicability conclusion.

## Final disposition

**REAL-DATA READINESS PENDING**; controlled fictional demonstration is subject to final test evidence. CI execution, deployed TLS/Redis/mail/DB controls, encrypted/restorable backups, retention/consent/legal review, independent security review, beta feedback, monitoring/incident ownership and authorized human release decision remain gates. See [formal checklist](real-data-readiness.md).

Suggested commit: `security: complete Olumira day 42 security and privacy hardening`

Day 43 operational continuation: [release](render-deployment.md), [backups](database-backup-recovery.md), [alerts/incident ownership](incident-response.md), [rollback](deployment-rollback.md). These prepared procedures do not replace hosted verification or legal approval.

Day43.5 inventory extension: migration0022 adds profile-bound care plans/goals and
reference links plus author-private handoff drafts; optional timer seconds are copied
into immutable routine-session steps. See [commercial upgrade inventory, export and
retention rules](day43-5-commercial-upgrade.md). The schema now has49tables; the
original43-table inventory above is historical. Real-data readiness remains pending.
