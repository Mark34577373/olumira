# HTTPS signup repair — 2026-10-22

## Root cause and evidence

Production responses sent `Referrer-Policy: no-referrer`, including the hosted
`/auth/register` page inspected with an anonymous HEAD request. Flask-WTF's default
`WTF_CSRF_SSL_STRICT=True` requires a same-origin Referer on HTTPS POSTs **after**
validating the CSRF token. Browsers honored the policy and omitted that header,
so correct account forms were rejected before the registration route ran.

Reproduced with Chromium against an isolated local HTTPS server: 375px signup
submitted `display_name`, `email`, `password`, `confirm_password`, `csrf_token` to
`POST /auth/register`; policy `no-referrer`, Referer absent, response 400, no account
created. The repeatable former-policy mode also logs the fixed reason code
`referrer_missing`. No private form/token/cookie values are printed.

This was exposed by HTTPS/proxy handling; it is not a PostgreSQL constraint,
missing field, JavaScript serialization problem or invitation gate. Existing
HTTP-only browser tests did not exercise Flask-WTF's HTTPS-specific check. Test
clients that explicitly supplied Referer also missed the browser policy conflict.

## Small correction

- `olumira/__init__.py`: use `Referrer-Policy: same-origin`. Same-origin forms can
  send Referer; cross-origin destinations receive no Referer. Leave strict HTTPS
  CSRF checks, signatures, expiration, session security, CSP and HTTPS enforcement
  enabled. Add fixed allowlisted CSRF reason codes to logs without submitted values,
  arbitrary exception text, referrer URLs, credentials or tokens.
- `olumira/routes/auth.py` / `templates/auth/registration_closed.html`: preserve
  `REGISTRATION_ENABLED=False` for both GET/POST; return a clear 403 explanation
  and existing-account sign-in/access-information links instead of silently
  redirecting to Contact. Invalid CSRF still fails before this handler.
- Update header/gate expectations and add real HTTPS browser and form regressions.
  No model, migration, password hashing, authorization or rate-limit changes.

Earlier historical security notes describing `no-referrer` are superseded by this
repair. Same-origin requests include their path/query, so existing access-log
redaction remains important. Recovery/invitation secrets remain URL fragments
and are not included in HTTP Referer headers or access logs.

## Registration and invitation audit

Template field names match RegistrationForm, including confirmation and hidden
CSRF. Submission is a native POST to `auth.register`; scripts do not intercept or
omit credentials. CSRF tokens are session-bound, signed and time-limited. Production
requires a stable configured SECRET_KEY; workers must share it. Changing that key
invalidates existing session/token state and is tested as a rejection, not bypassed.
No live secret values or private database records were inspected.

There is **no separate invite-only beta signup mechanism** in this repository.
`REGISTRATION_ENABLED` closes all new-account registration. Workspace invitations
are a separate authorized collaboration flow for a verified account with the
matching email; they do not bypass closed signup. Valid acceptance/reuse, invalid,
expired, revoked, email-mismatched and new/unverified-account invitations are
covered by existing regressions. No new invitation bypass or fabricated beta
credential is introduced.

## Verification

- Before fix: actual HTTPS browser signup returned 400 with all expected fields
  and no Referer; no new account was stored.
- After fix: Chromium native signup at 375px and 1440px returned 302 to
  `/auth/check-email`, with Referer present and persisted unverified hashed accounts.
  Secure host-only session cookies retained. No horizontal mobile overflow.
- Isolated SQLite fixtures migrate through 0022; real registration creates the user,
  workspace and starter routines. Duplicate submissions retain the existing generic
  response and do not duplicate accounts.
- Focused coverage: valid registration/verification/login; missing display name,
  invalid email, weak password, mismatched confirmation; missing/invalid/expired
  token, lost session, changed signing key, missing and foreign Referer; closed
  registration cannot be bypassed with an invitation parameter. Invalid fields
  render 422 inline errors; CSRF rejection remains a readable 400 refresh message.
- Missing required email/password and existing registration/login rate-limit,
  hashing, duplicate, session and privacy cases remain in the existing auth suite.

Commands:

```sh
venv/bin/python tests/browser/check_signup_https.py --reproduce
venv/bin/python tests/browser/check_signup_https.py
venv/bin/python -m pytest -q tests/test_signup_https.py tests/test_authentication.py tests/test_public_experience.py tests/test_security_hardening.py tests/test_proxy_redirects.py tests/test_account_recovery.py
venv/bin/python -m pytest -q tests/test_workspaces.py -k 'invitation_encrypted_delivery_accept_and_reuse or invitation_mismatch_expired_revoked_and_invalid or new_account_invitation_and_unverified_gate'
```

The HTTPS fixture uses a self-signed **local test certificate** and browser
`ignore_https_errors` only for that disposable loopback server. Application and
production TLS verification are unchanged. Mail uses the isolated encrypted
**development queue**; actual external delivery is not claimed.

Results: combined signup/auth/public/security/proxy/recovery run: **71 passed,
8 subtests passed**, 117.36s. Targeted workspace invitation run: **3 passed,
26 deselected**, 10.90s. Both runs emitted the existing OpenSSL legacy-provider
warning. Final mobile/desktop HTTPS browser run passed; former-policy reproduction
passed by confirming 400 and `referrer_missing` at both widths.
`git diff --check` passed. No failing tests were suppressed.

## Hosted status and operator steps

The hosted page was independently inspected and still sent the conflicting
`no-referrer` header. A hosted account was **not** created, and hosted signup after
this correction is **not verified**. Render logs/environment/database were not
accessed. No deployment, commit or push was performed.

After an operator deploys the reviewed change:

1. Keep `APP_ENV=production`, the stable SECRET_KEY, secure cookie/CSRF settings and
   `TRUSTED_PROXY_HOPS=1` for standard Render web ingress. Keep PUBLIC_APP_URL at
   `https://olumira.onrender.com` and use the reviewed Gunicorn config.
2. Confirm `/auth/register` returns `Referrer-Policy: same-origin`. Resolve any
   upstream header override rather than disabling Flask-WTF strict validation.
3. Reload the signup page for a fresh token and test an approved fictional account.
   Expect 302 to check-email, then separately verify actual email delivery and login.
4. If a 400 remains, check only the fixed CSRF reason code and request ID. For
   `session_missing`/invalid tokens, check cookies, consistent signing keys and
   token age. For `referrer_missing`, inspect browser/extensions/upstream policy.
   Do not paste passwords, session cookies or CSRF tokens into logs or chat.
5. If registration is intentionally closed, leave it closed; organizers must
   arrange account access using approved existing procedures. Workspace invitations
   alone do not provision a new account.

Sources: [Flask-WTF configuration](https://flask-wtf.readthedocs.io/en/1.2.x/config/)
and [Referrer-Policy semantics](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy).
