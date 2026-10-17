# Days 25–26: shared visual communication

## Day 25 — board builder

Communication now opens a shared board library for the active workspace/profile.
Search, category/status filters and pagination (18 boards/page) operate on scoped
server data. Board cards show their actual card count, picture preview, category,
profile context, Open action and authorized management controls. No usage statistics
or “recently used” claims are fabricated.

A caregiver can create an empty board or start with Basic Needs, Feelings, Daily
Activities or My Words. Boards support a name, description, category, authorized
profile association, and adaptive/2/3/4-column layouts. The editor offers labeled
card fields, original SVG picture choices, spoken text, pastel colors, duplication,
removal, pointer/touch handles and keyboard/native Move up/down alternatives.
Its live draft preview updates without writing to the server. Save confirmation
appears only after the server commits. Without JavaScript, draft controls round-trip
the form without saving; Save persists the entire validated draft atomically.

Cards have stable IDs and unique positions per board. Reordering temporarily moves
positions outside the valid draft range inside one transaction, then applies final
order; failures roll everything back. Source-card IDs from other boards are rejected.
Every accepted edit increments a board version. Stale forms return 409 with the
caregiver's draft retained and a link to the latest saved editor. Native forms have
CSRF protection; the editor warns before discarding unsaved changes and disables
repeat Save activation. UUID creation keys make retried creation idempotent.
Workspace-first locks serialize editing, membership changes, duplication and archive.

Board duplication creates fresh card IDs in an authorized target profile. Archive
is reversible and retains all cards; archived boards are readable with interactions
disabled. Only 40 active boards per profile/workspace context and 48 cards per board
are allowed. Empty boards show useful guidance. Server validation bounds labels,
spoken text, metadata, layouts, picture IDs, colors, card arrays and request sizes.

The original ten quick choices and account/profile-scoped browser custom choices
remain available at **Communication → Quick choices & existing browser cards**
(`/communication/quick`). Existing localStorage keys/data are unchanged. They are
not silently imported into shared board records: publishing personal browser content
requires an explicit future import flow or caregiver recreation in the editor.

## Day 26 — independent communication experience

**Open board** goes to `/communication/<id>`, independently of `/edit`. It opens in
focus view by default, showing large picture cards, the phrase strip and a prominent
**Speak message** button. There are no editor links or card-management controls.
Exit board returns to the library; Exit focus view restores global navigation and
workspace controls. Escape also exits focus, and no Fullscreen API is required.
Speech settings remain available through an ordinary disclosure. Focus toggling
never navigates away or changes the message. Mobile layouts cap grids at two
columns and keep cards readable rather than squeezing a four-column desktop grid.

Card activation by native click/tap/Enter/Space appends exactly one token, shows a
visible “Added” mark, updates the written message and speaks the configured words
when enabled. Moving keyboard focus alone never speaks. Multiword cards retain
their original text; no AI rewriting or punctuation normalization is performed.
Message tokens can be removed individually, removed from the end, or cleared.
Messages are bounded to 40 tokens/1,000 characters, with clear limit feedback.

The active message is held **only in page memory**, never localStorage, server
sessions, URLs, analytics or an utterance-history table. It clears on reload/exit.
This behavior is stated beside the message. Speech preferences alone (on/off,
voice identifier, conservative rate) may persist locally in an account/workspace/
profile namespace. Blocked browser storage does not prevent communication.

Browser Web Speech API integration supports individual cards, complete messages,
Stop, Replay, on/off, local voice selection and rates 0.8/1/1.15. Each new request
cancels older speech; generation checks ignore callbacks from cancelled requests.
Only voices for which `SpeechSynthesisVoice.localService === true` are offered.
There is no automatic fallback to a remote/default voice. Asynchronously loaded
voices update the controls. Missing voices, unavailable APIs and speech failures
leave the written message usable and show simple retry guidance. No paid or
third-party speech/AI API is used. Device audio and offline availability depend on
the actual browser/OS; mocked API tests do not prove sound output on every device.

Caregivers explicitly save meaningful phrases, keeping the current message visible.
An accessible native dialog posts with CSRF; progressive enhancement saves in place
and adds the phrase only after a confirmed server response. Network errors retain
the dialog/message and the same idempotency key for a safe retry. Native form fallback
remains available. Saved phrases belong to the selected profile (or the explicitly
selected workspace-wide context), and are shared only with authorized members.
Phrase management supports label/text edits, ordering, archive and restore, with
versions and a 50-active-phrase limit. Archived management shows the latest 50.
No quick phrases are forced into real accounts; starter/demo content is opt-in.

Selecting a saved phrase replaces the current message with its exact saved text,
ready to speak. Caregivers can manage phrases; viewers can select cards and phrases
but cannot save/edit them. Server permissions enforce this independently of UI.

A lightweight visible-tab check every 30 seconds verifies board access/version.
Known access loss/expiry/archive clears the draft, stops speech and disables use;
a changed board disables stale picture cards and asks for reopening, retaining the
written message. Network interruption shows guidance without claiming a save.
No request is made per card selection or word removal. Already downloaded content
cannot be retroactively erased from an offline device before a successful check.

## Schema, security and media

- `0010`: `communication_boards` and `communication_cards`.
- `0011`: `saved_communication_phrases`.
- Foreign keys, profile/workspace triggers, unique board/card ordering, bounded
  queries and scope/order indexes. SQLAlchemy board/card relationships are explicit;
  accidental lazy-loading is disabled in favor of deliberate scoped queries.
- Existing verified authentication, refreshed memberships, permissions and profile
  scoping apply to every page and record lookup, including guessed IDs and JSON.
- All writes use CSRF, current authorization under the workspace lock and
  transactions. Version conflicts preserve drafts. Form context binding rejects
  stale workspace/profile selection rather than saving to another tab's context.
- Stored labels/text are escaped by Jinja; browser rendering uses `textContent`.
  Private communication text never appears in URL query strings or application logs.
- Existing CSP, private no-store responses, secure sessions and safe errors remain.
- The symbol library is original project SVG markup with stable allowlisted IDs,
  readable labels and no external image URLs or proprietary AAC assets.
- Custom uploads are disabled. No file input/upload route exists. Future support
  requires durable private object storage, authorized delivery, content-verified
  bounded raster formats, safe generated keys and metadata stripping. Render's
  ephemeral disk must not become the persistent image store.

## Deployment and local verification

No new dependencies, secrets, environment variables, workers or paid services.
Continue using the existing Flask/Gunicorn, PostgreSQL/SQLite, Redis/authentication
and mail configuration. Email delivery is separate from browser speech; local demo
verification does not establish real SMTP delivery.

1. Quiesce writers and take a private, verified complete DB backup. Preserve the
   independent existing encryption/signing keys according to the current runbook.
2. Review migrations and run `venv/bin/python -m flask --app app db upgrade`.
   Current head is **0011**. No schema mutation happens automatically on startup.
3. Restart the existing `gunicorn app:app` deployment or local Flask process.
4. Verify login, both profile contexts, templates, board/card editing and order,
   concurrent edits, archive/restore, viewer denials and another family's 404s.
5. Open the independent board, test keyboard/touch phrases, real device audio,
   Stop/Replay/on-off/local voice/rate, offline/error guidance and saved phrases.
6. Inspect narrow/landscape layouts, visible focus, picture labels, CSP and DB
   integrity. Review private logs without recording utterances or submitted forms.

The legacy-only transfer utility refuses new board/card/phrase records and requires
head 0011 rather than silently discarding this data. Both downgrades refuse
unreviewed deletion. Rollback requires stopped writers, an incident snapshot,
a verified pre-upgrade backup and matching old code/keys; reconcile any activity
created after that backup before discarding an upgraded database.

New assets: `board-editor.js`, `communication-board.js`, shared stylesheet additions
and original server-rendered SVGs. No permanent sidebar or framework rewrite.
Do not automatically commit, push or deploy.

## Repeatable fictional demonstration

Run `venv/bin/python scripts/preview_routines.py --port 5054`, then open
http://127.0.0.1:5054/auth/login. The script prints the path to a private temporary
credentials file containing fictional owner/caregiver/viewer access. It uses an
isolated temporary DB, normal verified accounts and existing permission checks;
it never opens the real database. Preview changes last until the process stops.

1. Open Communication, choose Basic Needs or My Words, and personalize six cards.
2. Move a card by keyboard or handle; save and reload to verify order.
3. Open the board: it starts focused, with no editing controls.
4. Activate I, want, water; use Speak, Stop, Replay and speech preferences if a local
   device voice is available. The written message works regardless of speech.
5. Save “Water please,” reload, and use the saved phrase.
6. Sign in as the demo caregiver to access the same profile's board/phrase.
7. Verify the viewer can communicate but cannot edit and a separate family is denied.

The browser runner reproduces this with fictional data and mocked speech APIs:

```sh
venv/bin/python -m pytest -q
venv/bin/python tests/browser/check_communication_boards.py
venv/bin/python tests/browser/check_ui.py
venv/bin/python tests/browser/check_workspaces.py
venv/bin/python -m pip check
venv/bin/gunicorn --check-config app:app
```

See [actual verification results](day-25-26-verification.md). Browser tests require
loopback sockets and installed Chromium. Real audible output, formal accessibility
certification and live PostgreSQL/Redis staging are separate operational checks.
