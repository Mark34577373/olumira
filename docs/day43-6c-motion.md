# Day 43.6C — public and authenticated motion

Verified locally on 2026-10-22 with fictional data. No commit, push, deployment,
production migration, credential change or normal database reset.

## Implementation

One shared `static/css/motion.css` / `static/js/motion.js` layer is loaded by both
base layouts, after existing styles. Public entrance duration is 450ms, stagger35ms
(capped at140ms), distance8px. Care workflows use180ms, stagger20ms (capped80ms),
distance4px. Entry opacity stays at least0.98 so text remains readable throughout;
content is never initially hidden. No number interpolation or fabricated activity.

| Surface | Enhancement |
| --- | --- |
| Public homepage | Eyebrow → headline → description → CTA → preview sequence; one-time section and showcase reveals; clickable-card lift; button press/hover feedback. |
| Features / How It Works / About | Shared section/step/value reveals; native navigation and actual destinations preserved. |
| Contact / legal | Shared link/button/navigation treatments; the contact form stays explicitly unavailable. |
| Public nature illustrations | Sun floats2px over8s, pale glow changes softly over10s, existing leaf layers sway0.65° with7/9/11s timings, dots drift1.5px over12s. No geometry/color redesign. |
| Auth / setup | Restrained card/step entry, progress transitions, existing saved-action spacing. Cards containing validation alerts skip entrance; errors do not receive success effects. |
| Dashboard | Brief bounded card stagger; exact statistics settle without counting up; native progress/ring transitions; actionable quick-card hover; confirmed checklist marks. |
| Care plans / tasks / handoffs | Gentle frame/title entry; existing wizard steps reveal on selection; real saved/shared alerts settle only after server confirmation. |
| Routine Studio / player | Keyboard reorder uses an optional180ms FLIP transform after immediate DOM reordering; pointer dragging highlights a dashed target and clears on finish/cancel; real progress and timer-state accents. No delayed completion requests. |
| Communication | Brief activation feedback without moving picture cards; accessible last-activated `aria-current` and existing textual check marker; state clears with an empty message. Phrase confirmation animates only after a successful JSON save. Speech indication follows actual start/end/error/stop, with no added audio. |
| Observations / timeline | Small card opacity settle, native filter reveal, GET loading status and real success flash. Care notes are not individually animated or rewritten. |
| Calendar | View-frame settle, event-link hover, native date/view navigation; GET loading status; dates/geometry are not interpolated. |
| Reports / analytics | Chart opacity settle only; exact plot geometry, labels and accessible count tables remain unchanged. Existing native export feedback is preserved. |
| Notifications | Native dropdown entrance; exact count badge settle; unread/read surface transitions. Dismissal remains explicit; important messages never time out. |
| Settings / account | Native navigation, checkbox accent transitions, form feedback and existing dialogs; no new tabs/router/dialog subsystem. |

`templates/components/garden.html` renders the original local SVG through a shared
Jinja macro. Public About, hero preview and auth illustration reuse it. The original
external `static/images/welcome-garden.svg` remains unchanged, including its use in
care workflow decorations. CSS does not attempt to target internals of an `<img>`.

## Accessibility and reliability

- OS `prefers-reduced-motion`, saved personal reduced-motion/reduced-effects, and
  board-specific reduced motion suppress effects. Preference changes cancel active
  Web Animations too. Saved personal preferences also apply to public pages while
  signed in, without fetching workspace notifications or care records.
- Public footer includes an explicit Pause/Resume motion control. Only its Boolean
  choice is stored locally; no care information or measurements are persisted.
- Decorative SVG animations pause offscreen and when the document is hidden.
  Without JavaScript, the original illustration stays visible and static.
- IntersectionObserver reveals happen once, without a hidden pending state. Missing
  observer support or script failure leaves everything visible.
- Focus rings remain immediate. Keyboard reorder alternatives, native dialog focus,
  Escape behavior, scroll restoration and browser navigation are preserved.
- Transform/opacity dominate effects. Tiny border/background accents reinforce real
  states; no height, chart dimensions, layout positions or statistic values are
  tweened. No heavy library, external service or new runtime dependency.
- No interaction waits for an animation. Pointer targets and focus semantics use
  actual DOM order immediately; animation is optional presentation only.
- No autoplay sound was added. Supported local browser speech still needs existing
  user interaction. The speech indicator reflects callbacks, not assumed playback.

## Server-confirmed feedback correction

The existing observation page trusted `?saved=1` to show a save confirmation. The
route now issues a generic success flash only after `journal.save()` succeeds; the
query parameter alone no longer creates that message or its animation. The existing
redirect destination remains unchanged. Data validation, persistence, permissions and
CSRF logic are unchanged. A focused regression covers rejected writes, real writes,
and replaying the saved query flag. No other account or authorization behavior changed.

## Files

- `static/css/motion.css`: shared tokens, entry/state/illustration effects, pause and
  reduced-motion rules; about7KB uncompressed.
- `static/js/motion.js`: progressive enhancement, viewport/document visibility,
  preference cancellation, optional feedback/reorder utilities and GET loading;
  about6KB uncompressed.
- `static/js/routine-builder.js`, `routine-timers.js`, `communication-board.js`:
  connect actual reorder, timer, activation, speech and confirmed phrase events.
- `templates/components/garden.html`, public About/components/base, auth layout and
  app base: shared illustration and asset inclusion, preference attributes/control.
- `olumira/__init__.py`: expose only the current user's existing display preferences
  on public pages; private notification context remains excluded.
- `olumira/routes/observations.py`, `templates/observations.html`: server-confirmed
  observation feedback replaces the URL-only confirmation.
- `tests/test_journal.py`, `tests/browser/check_motion.py`: confirmation and full
  fictional motion/workflow regression coverage.

## Verification

- `venv/bin/python -m pytest -q`: **235 passed, 2 skipped, 37 subtests passed**,508.54s.
  The opt-in PostgreSQL tests were skipped because disposable databases were not
  configured. One existing OpenSSL legacy-provider warning was emitted.
- `venv/bin/python -m pytest -q tests/test_ui.py tests/test_navigation_refinement.py tests/test_public_experience.py tests/test_communication.py tests/test_routine_studio.py`:
  **33 passed,24 subtests passed**.
- `venv/bin/python -m pytest -q tests/test_journal.py tests/test_public_experience.py tests/test_personal_settings.py`:
  **14 passed,8 subtests passed**, including the final confirmation/preference changes.
- `venv/bin/python tests/browser/check_motion.py`: **PASS — 80 layouts, all listed
  workflows, zero JavaScript runtime errors.**
  Covers30 public/auth layouts and50 app layouts at320,390,768,1024,1440px; OS and
  stored preferences; persistent pause; offscreen SVG; no-JS/no-observer fallbacks;
  exact statistics; dashboard checklist; care-plan editing; keyboard/pointer reorder;
  timer completion; four real guided completions; picture activation/clear;
  successful and rejected phrase saves; mocked local speech events; observation save;
  task completion; handoff sharing; notification read/dismiss; calendar navigation;
  settings persistence; zero JavaScript runtime errors.
- Bundled Playwright Node `--check` passed for all four changed/new JavaScript files.
- Updated isolated localhost5054 preview: login/dashboard/inline garden and immediate
  cancellation of an active animation after a preference change all passed. Test
  credentials are supplied in chat, not stored in the repository.
- `git diff --check`: passed.

Screenshots / machine-readable browser results are in ignored `artifacts/day43-6c/`.
The About illustration screenshot was directly reviewed. Browser speech was mocked
for the activity test, with no audio and no external speech service. This validates
callbacks/UI behavior, not actual device voice availability or audio playback.

## Deliberate limits

Native menu/details/dialog closing remains immediate. Animating height or delaying
hiding could keep controls focusable after collapse or shift care content. Opening
and summary/control state changes receive brief effects. Existing calendar/care-plan
editors remain their existing pages/wizard; no fake creation modals or inaccessible
client-side tabs were introduced merely for motion.

Full document cross-fades, view-transition snapshots, animated exit interception,
parallax and persistent loops in care workflows were omitted. Browser page navigation
keeps default scroll/focus/security behavior. Progress transitions apply when native
in-page values change and the browser supports pseudo-element transitions; server
reloads render their actual final value rather than inventing a zero-to-value count.

No Safari/Firefox, physical touch-device, assistive-technology or battery/CPU audit is
claimed. This is not WCAG certification. Existing contact, legal, SMTP, hosted-operations
and real-data-readiness blockers from43.6A–B remain; this milestone does not clear them.
