# Render Free transactional email over HTTPS

No migration, paid cron, SDK, or new dependency is required. Existing encrypted
outbox, expiring single-use tokens and account rate limits remain in use.

## Configure manually after reviewing/deploying these code changes

1. Create a Resend account at https://resend.com. Check the current free allowance
   at https://resend.com/pricing (100 messages/day when checked 2026-10-26).
2. For a private smoke test only, use `Olumira <onboarding@resend.dev>` as MAIL_FROM
   and send to the email address associated with your Resend account. That test
   domain cannot send to arbitrary users. For other users, verify a domain you
   control in Resend, apply its exact DNS records, and use a sender on that domain.
   An onrender.com subdomain is not a domain you control for DNS verification.
   Review provider privacy, retention and tracking settings before family use.
3. Create a sending-only API key (restrict its domain where available). Enter it
   directly in Render's secret environment settings; never paste it in chat/Git.
4. In the web service Environment set:

   ```text
   MAIL_BACKEND=resend
   MAIL_DELIVERY_MODE=request
   RESEND_API_KEY=<your private sending key>
   MAIL_FROM=Olumira <onboarding@resend.dev>
   ```

   Replace MAIL_FROM with your verified-domain sender for general registration.
   Keep MAIL_ENCRYPTION_KEY unchanged (existing queue payloads depend on it).
   Keep DATABASE_URL, strict TLS, SECRET_KEY, PUBLIC_APP_URL, Redis and proxy settings.
   SMTP variables are unused by this backend. Apply the environment changes with
   the approved deployment. No deployment or provider account was created here.
5. Request a fresh verification link at `/auth/resend-verification`. Old links may
   be expired. Check Resend's dashboard for acceptance, delivery or bounce events,
   then check inbox/spam. Do not share token links or provider message bodies.
6. Open the verification link, sign in, sign out, and sign in again. Test password
   reset separately. Provider acceptance is not proof of inbox delivery.

## Execution and failure behavior

Only new messages queued by a successful HTTP request are attempted, after the
service transaction commits, with at most three jobs per request. Delivery waits
for the provider with a five-second socket timeout; request latency increases.
No background threads, public dispatch endpoint or per-process scheduler is added.
Request scope prevents one user's action from draining another user's backlog.
A fixed HTTPS endpoint uses system certificate/hostname verification; redirects
are rejected and provider response bodies/errors are never logged. Job IDs supply
stable provider idempotency keys; this is not an unlimited exactly-once guarantee.

The existing worker also supports this transport. Failed attempts preserve the
outbox's backoff and maximum-attempt safeguards, but **there is no autonomous retry
scheduler on this free setup**. A user can request a fresh link through the existing
rate-limited flow, invalidating older links. Operators can run the existing
`flask --app app mail-send-pending --limit 20` in an approved environment to retry
due jobs. Jobs created outside HTTP requests still need the worker. Scheduled
reminders and retention/privacy maintenance still need their own operational plan;
this change does not replace scripts/run_operations.py for those tasks.

Request timing may differ when a provider call occurs; generic account-existence
responses are preserved, but this mode does not provide timing indistinguishability.
Use the worker mode for stricter timing separation and reliable autonomous retries.
To roll back, restore the previous SMTP/worker configuration and its functioning
worker; do not disable verification or change the encryption key.

## Verification

Local tests mock all provider/network calls. They cover committed signup delivery,
request scoping, failure/backoff/redaction, expiry cancellation, TLS verification,
HTTPS payload/idempotency, provider rejection, and existing account lifecycle.
Hosted delivery remains unverified until the owner configures a provider and
completes the smoke test above. No real messages were sent during implementation.

References: https://resend.com/docs/api-reference/emails/send-email and
https://resend.com/docs/knowledge-base/403-error-resend-dev-domain .

Executed locally on 2026-10-26:
- Focused HTTPS/request tests: 6 passed.
- Combined account recovery, retention, interactive release and initial HTTPS
  tests: 49 passed (included duplicate collection of the reused account fixture;
  that collection duplication was removed in the final focused test file).
- `git diff --check`: passed.
- The local OpenSSL legacy-provider warning persisted; no test failed from it.
