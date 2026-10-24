# Render PostgreSQL TLS trust investigation — 2026-10-23

## Findings and what remains unknown

The operator reports failed_tls_trust and confirms the URL contains both
sslmode=verify-full and sslrootcert=system. This establishes the existing
classifier saw a trust-related libpq error phrase; it does not establish a
specific issuer/root, a missing OS package or a successful hostname check.

- Requirements pin psycopg[binary]==3.3.6. The inspected **local Mac** runtime is
  psycopg 3.3.6, binary implementation, libpq 180006 (18.6). That is **not evidence
  of Render's installed version**. The enhanced startup log reports actual
  deployed versions; libpq 16+ supports sslrootcert=system.
- config.py normalizes the URL to postgresql+psycopg, enforces explicit verify-full
  in production, and sets timeouts and statement limits. Its connect_args contain
  no sslmode/sslrootcert overrides. No conflicting TLS configuration was found in
  this checkout. Actual deployed environment/service-group overrides are unknown.
- System trust means the roots used by libpq's SSL implementation. Binary psycopg
  bundles native libraries; Python ssl and the standalone openssl executable may
  use different libraries/default paths. A successful Python CA-store load is not
  proof that libpq found the right roots.
- Explicit URL options normally override PGSSLROOTCERT/PGSSLMODE defaults; engine
  connect_args can override URL options. SSL_CERT_FILE/SSL_CERT_DIR can affect
  OpenSSL's system roots. New logs report presence/source/override booleans only,
  never values. Service files and custom connection events require separate review
  if present; this repository does not install a custom TLS connection hook.
- Preserve the exact **External Database URL hostname**. Render's internal endpoint
  does not support verify-full. An IP, hostaddr/query-host override, internal alias
  or unrelated certificate cannot repair hostname verification. Do not set sslsni=0.

The precise external endpoint's issuing CA has **not** been authenticated or
identified here. The official Render connection docs reviewed describe managed
external TLS but do not supply an endpoint-specific CA bundle in the reviewed
section. No guessed Let's Encrypt/AWS/RDS/private CA bundle was downloaded or
installed, and no server-presented certificate was promoted to a trust anchor.

## Diagnostic additions

The existing OLUMIRA_DB_DIAGNOSTIC=1 startup-only/read-only probe now emits:

| Stage | Sanitized evidence |
| --- | --- |
| tls_runtime | Installed psycopg/libpq versions, implementation, whether libpq supports system roots |
| tls_parameters | Effective mode/root source, hostname-verification requirement, duplicate TLS arguments, SQLAlchemy override and environment-presence booleans |
| linux_system_bundle | Existence/readability/PEM parsing and certificate count for /etc/ssl/certs/ca-certificates.crt; no certificate identities/data |
| configured_ssl_cert_file | Same checks for SSL_CERT_FILE when set; its path is never printed |
| tls_root_bundle | Same checks for an explicit/default libpq CA file; its path is never printed |
| python_trust_hint | Python default CA count, explicitly labeled non-authoritative for libpq |

Parsing a bundle proves neither its provenance nor that it trusts this database.
No CA store, environment variable, connection option or authentication code is
changed automatically. The diagnostic proceeds to the existing real connection,
SELECT 1 and schema inspection; that handshake is the actual verification test.
No new endpoint, credential output, database mutation or migration is added.
Trust failures also include a fixed tls_trust_detail hint: root_file_missing,
root_file_unreadable/root_file_error, certificate_expired/not_yet_valid,
self_signed_untrusted, issuer_chain_untrusted or verification_failed_unspecified.
An unspecified verification error does not identify an issuing CA. Expired or
wrong-host certificates require provider/endpoint correction, not arbitrary roots.

## Render Free: exact controlled procedure

1. Operator releases the reviewed diagnostic changes using the existing deployment
   process. In **web service → Environment**, set OLUMIRA_DB_DIAGNOSTIC=1 and choose
   Save and deploy. No Shell subscription is required; read startup entries in Logs.
2. Confirm tls_parameters reports sslmode=verify-full, hostname verification true,
   root_source=system, no unexpected SQLAlchemy override or duplicate TLS arguments.
   Resolve conflicting service/environment-group settings privately. Do not paste
   DATABASE_URL or any credential into chat/logs.
3. Confirm deployed libpq >=160000. If older, investigate the installed dependency
   build/cache; requirements pin a modern psycopg but only the runtime version
   proves native support. Do not weaken SSL mode as a compatibility workaround.
4. Review root-file flags. A stale/missing SSL_CERT_FILE override or inappropriate
   SSL_CERT_DIR should be corrected to approved runtime trust material, considering
   every service using those variables. Do not disable TLS or certificate checks.

### Option A: explicitly select an existing authentic OS CA bundle

If linux_system_bundle reports parsed with a nonzero count, its provenance is the
trusted Render runtime image, and it contains the needed public trust anchor, an
operator can remove default-path ambiguity without changing global SSL variables:

```text
DATABASE_URL=postgresql://USER:PASSWORD@EXTERNAL_HOST:5432/DATABASE?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt
```

Substitute the original external URL/credentials privately. Replace the existing
sslrootcert argument rather than adding a second one. This file is conditional:
**do not assume it exists on every runtime**, and a parsed OS bundle does not prove
it includes the endpoint's issuer. Actual connection success under verify-full
is still required. If that path succeeds while system fails with otherwise equal
settings, the evidence supports a native default trust-location discrepancy.

### Option B: an authentic provider/CA bundle as a Render secret file

Use this only after identifying and authenticating the endpoint's trust anchor.
Ask Render through its authenticated support channel for the external endpoint's
issuing CA, the official root/intermediate PEM distribution URL, expected SHA-256
fingerprints and rotation procedure. Obtain roots from that authenticated provider
information or the issuing CA's official HTTPS repository and cross-check those
fingerprints independently. A server-presented chain may inform a private review
but is not itself trusted provenance. Do not trust a self-signed leaf, copy an
unverified chain, invent a bundle, or use a private client key as a CA file.

Once an appropriate authentic PEM bundle is available:

1. Open **web service → Environment → Secret Files → Add Secret File**.
2. Filename: **postgres-ca.pem**. Contents: the reviewed root CA PEM bundle, plus
   necessary authenticated intermediates if required. No server private key.
   Render exposes it at **/etc/secrets/postgres-ca.pem**. Review the file contents
   privately; CA certificates are public, but do not mix unrelated secrets into it.
3. Change only the root-file option in DATABASE_URL:

   ```text
   postgresql://USER:PASSWORD@EXTERNAL_HOST:5432/DATABASE?sslmode=verify-full&sslrootcert=/etc/secrets/postgres-ca.pem
   ```

   Preserve valid URL escaping, all required options and the exact hostname. Avoid
   duplicate arguments. A URL query uses `&`, never HTML `&amp;` in Render's value.
4. Save/deploy the reviewed settings. Adding a secret file triggers deployment;
   perform this manually. Each web/cron service needing this database trust must
   receive the file and equivalent verified settings; do not attach migrator
   credentials to a public web service.
5. Confirm root_source=file and tls_root_bundle parsed/nonzero, then connection
   connected and select_1 ok. Parsing alone is insufficient. A hostname mismatch
   must be resolved at the endpoint/certificate, never by switching to verify-ca.
6. Keep ownership of CA rotation/update review. Remove unused conflicting root
   settings once their effect on other components is understood.

## Safe acceptance and rollback

- Require a real diagnostic connection and SELECT 1 success with verify-full and
  the exact external hostname. Also confirm migration/schema status before testing
  approved fictional signup/verification/login. Do not run migrations to cure a
  failed TLS handshake. PostgreSQL pg_stat_ssl can prove encryption but by itself
  cannot prove client certificate verification; the successful strict connection
  configuration is essential.
- Keep the runtime unchanged apart from reviewed trust settings. On failure retain
  strict verification, collect only sanitized diagnostic entries and roll back to
  a known verified configuration if available. Do not fall back to require/disable.
- After collecting evidence, set OLUMIRA_DB_DIAGNOSTIC=0 (or remove it) and redeploy.
  Free-tier startup logs suffice; no public diagnostics or Shell access is needed.
- Hosted connectivity, actual deployed CA contents, issuer provenance, hostname
  verification and successful hosted authentication remain **unverified** here.
  No commit, push, deployment, migration or production secret-file upload occurred.

## Tests and files

Changed olumira/database_diagnostic.py, added olumira/tls_diagnostic.py and
tests/test_tls_diagnostic.py, and this report. Existing authentication/TLS policy
is unchanged. Unit fixtures use a clearly fictional self-signed CA only to test
PEM parsing; that material is never application trust or a proposed Render CA.

```sh
venv/bin/python -m pytest -qtests/test_tls_diagnostic.py tests/test_database_diagnostic.py tests/test_registration_diagnostics.py tests/test_infrastructure.py
```

Tests cover installed-version reporting, native-system support detection,
parameter precedence/overrides, missing/invalid/parsed CA files, environment flags,
redaction and existing read-only/schema checks. Final counts are recorded below. No live Render CA/handshake result is claimed.

Sources: [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html#binary-installation),
[PostgreSQL trust configuration](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-SSLROOTCERT),
[Render database endpoints](https://render.com/docs/postgresql-creating-connecting),
[Render secret files](https://render.com/docs/configure-environment-variables#secret-files).

Verification results: combined diagnostic/infrastructure/privacy run **37 passed**
(12.76s); final TLS/database diagnostic run **28 passed** (6.05s), overlapping the
combined run. Both emitted the existing OpenSSL legacy-provider warning.
`git diff --check` passed. No new runtime dependency was installed.

## Confirmed production follow-up

The operator now confirms psycopg 3.3.6 binary/libpq 18.6, verify-full/system,
hostname verification required, no TLS override or duplicate arguments, and 148
parsable certificates in the Linux CA file. These supersede the earlier unknown
runtime versions. Trust failure remains verification_failed_unspecified.

Smallest next controlled configuration test: replace only sslrootcert=system with
sslrootcert=/etc/ssl/certs/ca-certificates.crt in the existing External Database
URL. Preserve verify-full, the exact external hostname and all other settings.
This uses existing runtime trust material; no new certificate or secret file is
needed for this test. Keep the temporary diagnostic enabled for one restart and
require connection=connected followed by select_1=ok before proceeding. Then
turn the diagnostic off. If it still fails, the available evidence does not show
that this bundle trusts the endpoint chain; obtain authenticated issuer/bundle
information from Render rather than adding a guessed certificate or migrating.
No claim is made about which native OpenSSL default file/directory was previously
used: system does not necessarily select this particular Linux PEM file.
