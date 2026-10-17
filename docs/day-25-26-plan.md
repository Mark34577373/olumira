# Days 25–26 concise audit and implementation plan

The original communication route renders ten built-in choices, with account /
workspace / profile-namespaced custom choices in browser localStorage. There are
no shared board tables, speech controls or phrase-strip data. Existing Flask
verification, current workspace membership, profile scoping, CSRF, forest/sage
components and native-form builder patterns can all be reused.

1. Add versioned board/card tables, bounded board library and draft editor with
   original SVG symbols, templates, persistent order, optimistic versions,
   idempotent creation, duplicate/archive/restore and scope/role enforcement.
2. Preserve the existing browser choices at `/communication/quick`, with a visible
   library link. Do not silently import private browser content into shared data.
3. Keep `/communication/<id>` independent of `/edit`: no editor controls in the
   communication view. Caregivers return to the library deliberately to edit.
4. Verify Day 25, then add Day 26: memory-only phrase strip, local-voice browser
   speech, accessible controls, focus view, explicitly saved profile-scoped phrases,
   preferences without utterance storage and graceful errors/unsupported speech.
5. Run focused service tests, fictional browser speech mocks plus keyboard/touch/
   mobile/no-JavaScript checks, full regressions and populated migration checks.
6. Back up the real local DB before additive upgrades, restart localhost, offer a
   separate fictional preview, document deployment/rollback and actual evidence.

User explicitly requested continuing through both days, overriding the original
Day 25 stop. No commit, push or deployment. Custom uploads remain disabled because
there is no configured durable private media backend; use original built-in SVGs.
