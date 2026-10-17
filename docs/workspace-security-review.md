# Workspace security review — October 17, 2026

This is a focused implementation review with automated evidence, not an independent
security audit. Hosted PostgreSQL/Redis/SMTP operation still requires staging checks.

## Threat model

| Threat | Implemented control | Evidence / limit |
| --- | --- | --- |
| Forged workspace cookie/selection | Reload active membership; invalid context falls back only to an authorized workspace; explicit forged selection is rejected | Workspace negative tests |
| Foreign routine/observation/profile ID | Query predicates combine active workspace and selected profile; server checks before mutation | Direct POST and read tests; profile association DB enforcement |
| Viewer/caregiver escalation | Central deny-by-default matrix; owner-only invite/admin; owner grants unavailable | Role matrix and direct HTTP tests |
| Stale access after demotion/removal | Database permission checks per request and repeated checks under workspace write lock | Active-session unit and browser tests |
| Ownerless workspace | Automatic atomic owner membership; no owner removal/demotion/transfer path | Owner-protection tests |
| Invitation guessing/leak/replay | 256-bit randomness, verifier digest, encrypted outbox, fragment URL, history clearing, generic invalid response, conditional single-use claim | Token/expiry/rotation/concurrency tests; recipient email still inherently contains link |
| Wrong-email or unverified acceptance | Verified login and current account-email match under lock; inviter must still be an active owner | Negative acceptance tests |
| CSRF and GET mutation | Existing global CSRF; changes use POST; invitation GET only presents guidance/form | All new mutation endpoint tests |
| Brute force/spam | Existing auth/recovery limits plus invite/resend and workspace-creation limits; production requires shared Redis | Real request counters tested in development; live Redis unverified |
| XSS/input abuse | Escaped Jinja text, bounded inputs, allowlisted roles/avatars, no uploads, CSP self-only scripts | Validation/escaping tests; no clinical data required |
| Partial collaboration writes | Transaction boundaries include workspace + owner membership and invitation + encrypted delivery; workspace row lock orders mutations | Forced rollback and simultaneous acceptance tests |
| Accidental legacy disclosure | Only explicit existing account/owner associations backfilled; unknown/null ownership remains unassigned | Populated 0003 upgrade test and legacy isolation tests |
| Secret exposure in logs/errors | Generic error handlers; redacted queue errors; audit events contain IDs/type/time only | Existing account redaction and new audit tests |
| Audit tampering | Owner-only viewing, no mutation routes, database update/delete rejection | Immutability test; database administrators remain trusted |
| Cached private pages/search indexing | no-store, no-referrer, X-Robots-Tag, frame denial, CSP; existing bfcache reload guard | Header and account tests |
| Database/schema failure | Versioned additive changes, explicit backup, no startup migration, preserved completions, refused destructive downgrade | Migration snapshot/foreign-key/model checks |
| Upload abuse | Only built-in illustrated avatars; no uploaded files accepted or served | Avatar validation tests |

An in-flight request authorized just before a role change may finish. Subsequent
requests reload membership. Previously delivered emails and downloaded/browser-local
content cannot be recalled. No client-side control is treated as authorization.
Workspace write serialization prioritizes correctness over throughput; load testing
and large-family pagination are future operational work.

## Endpoint authorization inventory

| Endpoint group | Gate |
| --- | --- |
| Auth/account routes | Existing account session, CSRF, current-password/token rules; workspace membership grants no account-control privileges |
| Dashboard, routines GET, observations GET | Verified login + live active membership + workspace/profile predicates |
| Routine add/template | routines.create under workspace lock |
| Routine edit/delete | routines.edit under workspace lock + scoped resource |
| Routine complete | routines.complete under workspace lock + scoped parent |
| Observation create/edit | observations.create/edit under workspace lock + scoped record |
| Communication | Verified membership; transient selection is read-only; browser customization explicitly local and role-gated |
| Resources | Verified membership; common static information only |
| Workspace list/create/select | Verified login; list only active memberships; create atomic owner grant; select validates membership |
| Workspace settings POST | workspace.manage rechecked under lock |
| Profile create/edit/overview/select | profiles.create/edit/view, active workspace, allowlisted avatar and bounded fields |
| Invite/resend/revoke | members.invite rechecked under lock; role/email validation; rate limits |
| Invitation GET | Public generic guidance; no token lookup disclosure or mutation |
| Invitation POST | CSRF + verified account + matching email, current inviter authority, locked single-use claim |
| Member role/remove | members.manage rechecked under lock; non-owner targets in current workspace only |
| Audit / pending invitation visibility | Workspace owner only, via settings; no edit/delete endpoint |

## Dependency and static analysis review

`pip check` checks installed dependency compatibility; it is not vulnerability
analysis. [PyPA pip-audit](https://github.com/pypa/pip-audit) queries published
package advisories; its findings and absence of findings do not establish whole-app
security. Scanner tools are development dependencies only.

The initial audit reported cryptography 47.0.0 advisories. The compatible 48.0.1
wheel was installed and pinned, fixing the bundled OpenSSL advisory
[GHSA-537c-gmf6-5ccf](https://github.com/advisories/GHSA-537c-gmf6-5ccf).
Attempts to install 50.0.0 failed because this x86 Mac has no compatible wheel and
lacks native OpenSSL build prerequisites. No compatible 49.0.0 wheel was available.
The existing environment was left functional on 48.0.1, and account/email/browser
regressions were rerun afterward.

The patched scan still reports three distinct advisory IDs (duplicates may appear
in the advisory feed):

- PYSEC-2026-3552: PKCS#7/S/MIME decryption oracle; fixed in 50.0.0.
- PYSEC-2026-3553: certificate-chain verifier resource exhaustion; fixed in 49.0.0.
- PYSEC-2026-3554: DNS constraint / wildcard certificate verification; fixed in 49.0.0.

Olumira calls Fernet for mail-payload encryption; it does not expose PKCS#7/S/MIME
or cryptography certificate-verifier APIs. SMTP TLS uses Python's standard verified
SSL context. This is a reachability assessment, not an exemption or proof that all
transitive uses are safe. Before production, use a supported platform/build with
cryptography 50.0.0 or later, rerun regression tests and audit, and document the
result. No advisories were suppressed or silently ignored.

Bandit reports seven low-severity string-heuristic findings (the production-blocked
development secret, rate-limit text, password-hash parameters and recovery/email
labels) plus three medium SQL-construction findings in the legacy transfer helper.
The SQL identifiers come exclusively from a fixed model/table/column allowlist, not
request values; inserted record values remain bound parameters. These findings
were reviewed, retained in the scan output, and not treated as executable user SQL.
A later scan may shift line numbers but should receive the same manual review.

Full machine-readable reports are generated locally under `artifacts/days17-21`.
Do not publish local mail previews, database backups, secrets or real-care data with
these reports. Public onboarding remains an operational privacy/security gate.
