# Operational response and alert ownership

Extends [Day 42 incident and recovery procedures](day42-security-review.md#recovery-incident-response-and-day-43-handoff).
No staffed on-call team, configured alert destination or vendor monitoring account
exists in this work. The developer must name primary operator, backup operator and
privacy/security decision maker, test an alert and acknowledge response expectations
before beta exposure. Do not invent staff or claim 24/7 support.

| Signal / provisional threshold | Response / verification |
| --- | --- |
| Readiness non-200 for 2 minutes / TLS expiry <14 days | Operator checks ingress/cert, PG/schema and Redis; no security bypass; escalate outage |
| HTTP 5xx >1% for 5 minutes (with minimum 20 requests) | Correlate generated request ID and route template, stop bad rollout, assess rollback |
| p95 HTTP >2s for 10 minutes | Inspect CPU/RAM, bounded pool and DB contention; measure before scaling |
| DB connections >70%, disk >80%, memory >85% sustained | Investigate leak/queries/storage, schedule reviewed capacity change; cost approval |
| Cron failure or no successful completion for 5 minutes | Review run history, retry idempotent DB work; do not start duplicate schedulers |
| Pending mail age >5 minutes / exhausted attempts >0 | Check provider/TLS/auth and recipient-independent counts; approved test delivery, retry policy |
| Reminder lag >5 minutes | Check timezone/DST/run history and 24h catch-up window; investigate missed occurrences |
| No independent backup upload for 26h / restore fails | High-priority recovery incident; do not declare durability until authenticated restore passes |
| Auth failures/spike, isolation report, key exposure | Apply Day 42 containment, preserve minimal evidence, independent security/privacy review |

`olumira.operations` emits JSON timestamp/severity/category/operation/request ID/
route template/status/duration. It ignores client request IDs, private URLs,
query strings, bodies, cookies and exception payloads. X-Request-ID permits support
correlation. Security event logs use fixed event codes/internal IDs; Gunicorn
access logs remain minimized plain text. DB/SMTP errors remain redacted. A structured
request line does not make every third-party log private: inspect platform/proxy/
DB slow-query logs and configure restricted access/retention before real traffic.
No Sentry or automatic exception upload is enabled. External error integration must
use an explicit field allowlist, no default PII/breadcrumb bodies, and reviewed
vendor contract/retention. Start with restricted platform metrics and probe history;
log retention proposal seven days pending policy approval.

Readiness checks current migration heads and live DB plus Redis PING when configured;
liveness is dependency-free. Responses are generic 200/503. SMTP is deliberately
not contacted by probes: monitor actual worker results and approved synthetic
email tests separately. Hosted configuration is startup-validated. Probes do not
prove sender reputation, available backups, legal compliance or every schema
constraint. High-frequency probes also need capacity accounting.

During incidents: record UTC timeline, affected scope, operator, actions and evidence
access. Contain before retrying, preserve source, communicate known impact without
speculation, recover in isolation, verify permissions and data, then get human
reopening approval. A qualified reviewer determines notification duties and timing.
Post-incident work assigns owners/dates and tests the corrected failure mode.
