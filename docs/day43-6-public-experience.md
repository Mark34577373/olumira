# Days 43.6A–B — public website and account journey

Assessment: 2026-10-22, America/Chicago. Local fictional-data verification only.
No commit, push, deployment, purchase, production secret change or database reset.

## 1. Executive summary

Added a separate Flask/Jinja public website, shared brand tokens, original labeled
HTML product illustrations, responsive navigation, supporting pages and a cohesive
account layout. Connected the existing account system to saved onboarding without
replacing authentication, workspaces, profile scoping or the dashboard.

Part A's route/link/privacy/contact checks and 49 responsive layouts passed before
continuing Part B verification. The final public browser rerun also includes button
contrast checks. Contact delivery and legal approval remain explicitly unavailable /
pending; their UI never claims otherwise.

## 2. Public website and routing

| Route | Behavior |
| --- | --- |
| `/` | Public homepage for anonymous visitors; existing dashboard for signed-in verified members. Invalid/expired session attempts still take the sign-in path. |
| `/welcome` | Public homepage for either session state; signed-in visitors get Open Dashboard and My account, without signup CTAs or private workspace content. |
| `/dashboard` | Additional protected entry to the existing dashboard. Existing `dashboard.dashboard` URLs still build `/`, preserving established links, bookmarks and tour behavior. |
| `/features` | Ten verified capability sections, practical examples and fictional HTML interface illustrations. |
| `/how-it-works` | Accounts, verification, workspace/profile selection, optional setup, role boundaries, everyday use and FAQs. |
| `/about` | Purpose, values and honest controlled-testing status; no invented people, endorsements or company history. |
| `/contact` | Clearly unavailable form and beta information. No submission storage, SMTP delivery or beta acceptance claim. |
| `/privacy`, `/terms` | Explicit drafts describing reviewed current behavior and matters requiring approval. Existing private `/settings/privacy` is unchanged. |
| `/robots.txt` | Disallow all crawling for the beta stage. Existing noindex response headers remain. |

The public base has its own header/footer and no workspace selector, notification
previews, account identity or care-record queries. Public responses remain no-store,
including session-aware CTAs. A production-configured canonical origin supplies
canonical/Open Graph URLs; loopback development origins do not. No production domain
was invented. A small local PNG social asset depicts only the labeled fictional
public homepage. No private routes appear in a sitemap; a beta sitemap is intentionally
omitted while indexing is disabled.

The homepage includes a hero, six-feature introduction, five alternating showcases,
three-step explanation, transparent access/limitations section and closing CTA.
Public pages and the app use the same extracted `tokens.css`; app styles retain their
existing values. No frontend framework, external font, tracking service or new runtime
dependency was added. Below-fold product previews are HTML/CSS rather than downloads.

## 3. Authentication

`services/account_journey.after_login()` is the single default login decision:

1. Require email verification.
2. Honor the fixed intended invitation-acceptance route.
3. Resolve authorized workspace context; if none exists, open workspace management.
4. Honor an exact allowlisted intended destination.
5. Otherwise resume unfinished setup, or open the dashboard after completion,
   intentional skip or legacy exemption.

Login `next` stays an exact fixed-path allowlist. External, protocol-relative,
encoded, query-bearing and logout redirects are rejected as before. Existing safe
intended destinations can bypass optional onboarding, never authorization.
Invitation codes remain in email fragments / explicit forms, not URLs sent to the
server or a new session-based token store. Unverified invitees must verify and reopen
the original invitation as explained by the existing acceptance page.

Existing signup is open: this audit found no invitation-only account-creation gate.
Its behavior is preserved. New `REGISTRATION_ENABLED=false` closes both GET and POST
registration and changes public/signup links to honest beta availability information.
It does not silently provision access, implement invite-only registration or pretend
to collect beta requests. The default is documented in `.env.example`.

Account pages share the public visual shell while using existing WTForms, field
macros, password controls and POST forms. Account/security settings retain the private
app shell. Generic email responses no longer promise delivery. A registration email
queue failure is redacted and returns the same generic check-email journey; the
unverified account does not receive an authenticated session and can request a fresh
link later. A development banner explains that no external email is sent.

Password hashing, credential/IP limits, CSRF, purpose-bound expiring single-use
recovery links, session rotation/revocation, account-enumeration defenses, production
cookie/TLS/Redis/PostgreSQL guards and security headers remain in force.

## 4. Onboarding and dashboard

Reused the existing seven saved setup steps and completion screen; no new onboarding
model or reinterpretation of persisted step indexes. The final exploration step now
introduces optional Care Plans through its existing authorized route. Setup continues
to support selection of existing records, explicit fictional profile creation,
optional-step skip, resume and restart without rebuilding the platform.

Preserved the previous wrapping 16px action spacing: Enter Olumira primary, product
tour text link and Revisit setup outline button. Completion opens the existing
profile-aware dashboard. The horizontal app navigation, workspace/profile selectors,
role gates and existing first-use/empty-state actions remain intact. The account
menu adds Dashboard, Help and resources, and an Olumira website shortcut.

## 5. Important files

- `olumira/routes/public.py`: public blueprint, verified feature content, contact
  validation/unavailable response and beta robots rule.
- `templates/public/`: public base, reusable headings/CTA/previews/steps, homepage,
  features, how-it-works, about, contact and draft legal pages.
- `static/css/public.css`, `static/js/public.js`: isolated public layouts, responsive
  navigation, reduced motion and progressive enhancement.
- `static/css/tokens.css`, `static/css/premium.css`: extract/reuse existing brand
  values rather than duplicating or altering the app's palette.
- `static/images/social-preview.png`: fictional public-page social preview.
- `olumira/__init__.py`, `olumira/routes/dashboard.py`: register public routes and
  narrowly allow anonymous homepage rendering; protected dashboard alias remains gated.
- `services/account_journey.py`, `olumira/routes/auth.py`: centralized account entry,
  safe intended paths, optional registration closing, honest delivery language.
- `olumira/config.py`, `.env.example`: documented registration switch.
- `olumira/forms.py`: bounded contact validation and honeypot, retaining global CSRF.
- `templates/auth/`, `templates/workspaces/accept.html`, `templates/onboarding/setup.html`,
  `templates/base.html`: existing account/setup/app integration.
- `tests/test_public_experience.py`, `tests/browser/check_public_experience.py`,
  `tests/browser/check_account_journey.py`: new route/security/layout/journey coverage.
  Existing auth/recovery protection probes now use `/dashboard` because anonymous `/`
  is intentionally public; assertions still require denial of protected data.
  Existing browser login assertions now expect saved setup before their feature journeys.

## 6. Security and persistence

No model or migration changes. Isolated migrated temporary databases were used for
new tests; no normal application data was reseeded or reset. Existing migration tests
remain part of the full suite. Public forms retain global request-size limits, CSRF,
server-side lengths/email/category validation, a honeypot and IP rate limiting. While
contact is unavailable, even a manually submitted valid POST returns 503; invalid
input returns 422, invalid CSRF 400 and throttled requests 429. Submitted personal
content is neither persisted nor reflected in the unavailable response. Opening the
form for delivery requires an approved operator/retention workflow, not just a UI toggle.

Tests explicitly check that public pages never contain a fictional private profile
sentinel, private account email, workspace controls or notification context. Existing
cross-workspace, invitation-role, token replay, session expiry, reset and mutation-CSRF
tests remain in the suite. The repository's high-confidence tracked-file scan passed;
that scan does not establish that arbitrary secrets are absent from every artifact.

## 7. Accessibility and visual review

Chromium checked public pages at 320, 375, 390, 768, 1024, 1280 and 1440px, including
horizontal overflow and normal-state primary-button contrast >= 4.5:1. Mobile
navigation checks cover visibility, aria-expanded, keyboard focus, Escape, breakpoint
resize and no-script availability. Initially found and fixed a decorative hero
background overflow and a focus ordering issue on resize; legacy auth-page `nav`
padding is isolated from public navigation.

Account layouts were checked at the same widths, along with setup and dashboard
transition layouts. The prior focused care CTA test verifies normal/hover contrast,
focus visibility, keyboard order, saved-setup spacing and restart submission.
Desktop/mobile screenshots of every public page plus login/signup are saved locally
in ignored `artifacts/day43-6/`; every public page plus login and signup screenshots were directly
reviewed. Semantic landmarks, headings, labeled forms, inline errors, native FAQ
controls, skip links, motion preference and visible focus are retained/provided.
This is not an independent WCAG certification or manual assistive-technology audit.

## 8. Verification

Final command results are recorded below after execution. Early failures were fixed,
not counted as passing: anonymous-root assumptions moved to the protected dashboard
alias; invitation copy retained its established action; a test fixture now uses the
actual membership status `revoked`; responsive issues are described above.

- `venv/bin/python tests/browser/check_public_experience.py`: PASS, 49 public layouts,
  contrast, menu keyboard/resize/no-script checks, zero JavaScript runtime errors.
- `venv/bin/python tests/browser/check_account_journey.py`: PASS, 42 account layouts,
  actual registration → required verification → login → saved setup → selected-profile
  dashboard → feature → account → logout → returning login → password reset → login.
  Tokens came from the isolated encrypted development queue; no SMTP was used.
- `venv/bin/python -m pytest -q tests/test_public_experience.py tests/test_workspaces.py::WorkspaceTests::test_new_account_invitation_and_unverified_gate`:
  PASS, 9 tests + 8 subtests.
- `venv/bin/python scripts/scan_secrets.py --output artifacts/day43-6/secrets.json`:
  PASS, 316 tracked files checked, zero high-confidence matches; history not scanned.
- `venv/bin/python -m compileall -q olumira services tests/browser/check_account_journey.py tests/browser/check_public_experience.py`:
  PASS.
- `git diff --check`: PASS.

- `venv/bin/python -m pytest -q`: PASS, **233 passed, 2 skipped, 37 subtests
  passed**, 700.65 seconds. The two opt-in PostgreSQL tests were skipped because
  disposable `TEST_POSTGRES_URL` / `TEST_POSTGRES_SECURITY_URL` databases were not
  configured; this run does not claim live PostgreSQL verification. One existing
  OpenSSL legacy-provider warning was emitted.
- `venv/bin/python tests/browser/check_targeted_ui.py`: PASS, prior care CTA
  normal/hover contrast and focus; setup spacing at four widths, keyboard order,
  destinations and actual restart submission.
- Supplementary high-confidence scan of 18 new untracked files: zero findings.
  This and the tracked-file scan are limited pattern checks, not proof of no secrets.

## 9. Known limitations / external blockers

- Public contact delivery and beta-interest submission are unavailable. No approved
  mailbox, operator review or retention workflow was found; no delivery was simulated.
- Local verification/recovery work through the private development inbox. Actual
  SMTP sender/DNS/provider delivery and a hosted mail worker remain unverified.
- Privacy and terms are drafts requiring legal/operator review. This milestone does
  not assert legal compliance, medical validation or real-sensitive-data readiness.
- Hosted deployment, TLS/runtime verification, shared Redis, operational alerts,
  backup/recovery and independent security gates from Days 41–43 remain applicable.
- Python emitted an existing OpenSSL legacy-provider warning. No dependency/runtime
  reconfiguration was performed; maintained hosted native runtime review remains a
  separate release requirement.
- Chromium checks do not substitute for real-device, Safari/Firefox or assistive-
  technology review. Social metadata was checked locally; no external crawler was run.

## 10. Day 44 readiness

The implemented public/app journey can proceed with local controlled fictional-data
testing: the final regression results above are green. Contact/legal/hosted-email
and operations blockers prevent an unrestricted hosted or real-data launch claim.
No deployment is authorized or performed by this report.
