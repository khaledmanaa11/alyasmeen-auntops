---
phase: 03-agent-dependability-safety
plan: 04
subsystem: agent-safety
tags: [handoff, paused-session, whatsapp, unsupported-media, keyword-detection, conftest]

# Dependency graph
requires:
  - phase: 03-agent-dependability-safety (03-01, wave 1)
    provides: "handoff.trigger(phone, reason, metadata=None, assigned_to='aunt', notify=True) -> str"
  - phase: 03-agent-dependability-safety (03-02, wave 1)
    provides: "policy.detect_handoff_keyword(text) -> str | None"
provides:
  - "sessions.paused is read on every inbound message: load_session() SELECTs and returns it; handle_message() gates on it before any hard command or AI call"
  - "Keyword-triggered handoff: any non-None detect_handoff_keyword() result opens a durable handoff and sends exactly one deterministic acknowledgement (HANDOFF_ACK_REPLY)"
  - "Unsupported-media handoff: process_event's else-branch (audio/image/sticker/document/video/location/contacts) now calls handle_unsupported_media() instead of silently dropping the message"
  - "processor._open_handoff(phone, reason, metadata) -> bool — the shared try/except wrapper around handoff.trigger() every handoff call site in processor.py uses (this plan's two sites, plus 03-05's tool-escalation/AI-failure sites)"
  - "tests/conftest.py's autouse mock_db now patches app.services.handoff (query/execute/execute_returning); FakeDB models a handoffs table and pause-preserving session saves"
affects: [03-05-ai-failure-and-tool-escalation-handoff, 03-06, 03-07, 03-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Gate ordering inside handle_message: paused check -> keyword-handoff check -> hard commands -> stage-based inputs -> numeric menu pick -> AI fallback. Both new gates run before upsert-independent state is touched, so a paused/escalating customer can never accidentally mutate cart/order state."
    - "_open_handoff() wraps every handoff.trigger() call site in processor.py: trigger() is allowed to raise (03-01's contract), but the message pipeline never lets that raise reach the customer — it logs and falls back to a generic reply instead of promising an escalation that didn't durably happen."
    - "Reply-before-handoff ordering in handle_unsupported_media(): queue_text() runs before _open_handoff(), so a handoff write failure never costs the customer her apology."
    - "conftest.py's shared autouse mock_db is now the single seam every module that can trigger a handoff mid-pipeline gets patched through — same treatment 'audit' got in 05-09, now extended to 'handoff'."

key-files:
  created:
    - tests/unit/test_processor_safety.py
  modified:
    - tests/conftest.py
    - app/routers/whatsapp_helpers.py
    - app/services/processor.py

key-decisions:
  - "handoff and policy are imported at module level in processor.py (from app.services import handoff, policy) — safe because handoff.py only imports processor lazily, inside function bodies (_notify_aunt), so there is no import-time cycle."
  - "handle_unsupported_media() calls upsert_customer() itself rather than relying on a prior call, because process_event routes straight to it without ever calling upsert_customer — unlike handle_message, which always upserts first. Without this, a brand-new customer's first message being a voice note would violate handoffs.phone's FK to customers(phone)."
  - "handle_unsupported_media() re-checks load_session(phone).get('paused') on every call (not just relying on the caller) so a customer sending several voice notes during one active handoff gets exactly one apology + one handoff, not one per message."
  - "test_keyword_wins_over_hard_command_ordering documents, rather than proves, a genuine tie-break: hard commands match only on an EXACT lowered/stripped equality (cmd in (...)), while detect_handoff_keyword does substring/whole-word matching — the two vocabularies cannot literally collide on one exact string today. The test still pins that a message containing both a hard-command word and an escalation phrase routes to the handoff, guarding against a future substring-based hard-command match silently breaking this ordering."

patterns-established:
  - "Any new handoff call site in processor.py should go through _open_handoff(), not handoff.trigger() directly, to inherit the raise-swallowing contract."

# Metrics
duration: ~20min
completed: 2026-08-28
---

# Phase 3 Plan 04: Paused Gate + Deterministic Handoff Triggers Summary

**`sessions.paused` is now read on every inbound WhatsApp message (silencing the bot while still recording what the customer said), and two deterministic handoff triggers — an Arabic/English "talk to a human" keyword match and any unsupported media type (voice notes, photos, stickers, documents) — now open a real, durable handoff instead of the customer being ignored or the bot talking over a human who already took over.**

## Performance

- **Duration:** ~20 min
- **Started:** ~2026-08-28T18:35:53Z (estimated from the first commit's timestamp)
- **Completed:** 2026-08-28T18:44:20Z
- **Tasks:** 3 completed
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- `load_session()` (`app/routers/whatsapp_helpers.py`) now `SELECT`s `paused` and returns it in the session dict; `save_session()` gained a comment documenting that it deliberately never writes that column (only `handoff.trigger()`/`handoff.resolve()` own it).
- `handle_message()` gained two gates, in this exact order, both running before any hard command, stage-based input, or AI call: (1) **paused gate** — if `st["paused"]` is true, record the customer's message to `chat_history` and return without sending anything; (2) **keyword-handoff gate** — if `policy.detect_handoff_keyword(text)` returns non-`None`, open a durable handoff via `_open_handoff()` and reply with exactly one deterministic sentence (`HANDOFF_ACK_REPLY`), never a model-generated one.
- `process_event()`'s previously-silent `else` branch (anything that isn't `text`/`interactive` — voice notes, images, stickers, documents, video, location, contacts) now calls the new `handle_unsupported_media(phone, msg_type, name)`, which upserts the customer (mandatory — `handoffs.phone` has a live FK), records a `[رسالة <type>]` placeholder in `chat_history`, queues `UNSUPPORTED_MEDIA_REPLY` (before opening the handoff, so a handoff-write failure never costs the reply), and opens an `unsupported_media` handoff. The webhook event is still marked `processed = TRUE` either way — a media message can never become a poison pill.
- `_open_handoff(phone, reason, metadata)` is now the single shared wrapper every handoff call site in `processor.py` uses: `handoff.trigger()` is allowed to raise per its 03-01 contract, but the message pipeline swallows that and falls back to `AI_FALLBACK_REPLY` instead of promising an escalation that didn't durably happen.
- `tests/conftest.py`'s autouse `mock_db` fixture now patches `app.services.handoff` (`query`/`execute`/`execute_returning`) alongside `wh`/`processor`/`audit` — the exact gap `03-RESEARCH.md` flagged as "will break tests if missed." `FakeDB` gained a `handoffs` list serving `trigger()`'s idempotency SELECT and INSERT-RETURNING, and its session-insert branch now preserves an existing `paused` flag instead of resetting it on every save (mirroring `save_session()`'s real `ON CONFLICT DO UPDATE` clause, which omits that column on purpose).
- 20 new tests in `tests/unit/test_processor_safety.py` (`TestPausedGate`, `TestKeywordHandoff`, `TestUnsupportedMedia`) covering all three trigger paths, including handoff-write-failure fallback, re-entry-during-an-active-handoff suppression, and a first-contact-voice-note FK regression guard.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend tests/conftest.py — patch app.services.handoff, teach FakeDB about handoffs and paused** - `63cade3` (test)
2. **Task 2: Paused gate + keyword-triggered handoff in handle_message** - `90e74fb` (feat)
3. **Task 3: Unsupported media — reply and hand off instead of silently dropping** - `78e15ce` (feat)

**Plan metadata:** _(this commit)_

## Files Created/Modified
- `tests/conftest.py` — `mock_db` now patches `app.services.handoff` (query/execute/execute_returning) and documents why `app.services.policy` needs no patching; `FakeDB` gained `self.handoffs`, a `"FROM HANDOFFS"` query branch, an `"INSERT INTO HANDOFFS"` `execute_returning` branch, pause-upsert/pause-clear `execute` branches (checked before the generic 6-param session insert to avoid a param-count `ValueError`), and a pause-preserving session-insert branch; a new `last_handoff(fake_db, phone)` module-level helper sits next to `drain_outbox_jobs()`.
- `app/routers/whatsapp_helpers.py` — `load_session()` selects and returns `paused`; `save_session()` gained a load-bearing comment.
- `app/services/processor.py` — `HANDOFF_ACK_REPLY`/`UNSUPPORTED_MEDIA_REPLY`/`MEDIA_TYPE_LABELS` constants; `from app.services import handoff, policy` (module-level, safe — `handoff.py` only imports `processor` lazily); `_open_handoff()`; the paused + keyword gates inside `handle_message()`; `handle_unsupported_media()`; `process_event()`'s new `else` branch calling it, plus an `empty_text_message` log line for the pre-existing empty-body no-op.
- `tests/unit/test_processor_safety.py` (new, 268 lines, 20 tests) — `TestPausedGate` (4), `TestKeywordHandoff` (5), `TestUnsupportedMedia` (11, including a 6-way parametrization over media types).

## Interface for downstream plans (03-05 — verbatim)

```python
# app/services/processor.py
def _open_handoff(phone: str, reason: str, metadata: dict | None = None) -> bool:
    """Wraps handoff.trigger(); never raises. True on success."""

HANDOFF_ACK_REPLY = "تمام 🌿 حوّلت المحادثة لحنان، رح ترد عليكِ بأقرب وقت."
UNSUPPORTED_MEDIA_REPLY = "ما بقدر أفتح الرسائل الصوتية والصور والملفات 🙏 ..."
```

`handle_message()`'s gate order, load-bearing for 03-05 (which adds AI-failure and tool-escalation handoff sites to the same function/tool-executor):
1. `upsert_customer` / `get_customer_name`
2. `load_session` (now carries `paused`)
3. **paused gate** — return early, no reply
4. **keyword-handoff gate** — return early, one deterministic reply
5. hard commands, stage-based inputs, numeric menu pick
6. AI fallback (`generate_reply` + `_make_tool_executor`) — 03-05's territory

`tests/conftest.py`'s `mock_db` patch list is now `(wh, processor, audit, handoff)` for `query`/`execute`, plus `handoff.execute_returning` explicitly. Any test file exercising a path that can reach `handoff.trigger()` no longer needs its own local patch (though `test_handoff_trigger.py`/`test_handoff_resolve.py`'s dedicated local fakes remain valid and unaffected).

## Decisions Made
- `handoff`/`policy` imported at module level in `processor.py` — verified safe (no import-time cycle) since `handoff.py` imports `processor` only lazily inside `_notify_aunt()`.
- `handle_unsupported_media()` performs its own `upsert_customer()` call rather than assuming the caller already did — `process_event()` never called it on this path (unlike `handle_message()`, which always upserts first), and `handoffs.phone`'s live FK would otherwise reject a brand-new customer's first-ever message being a voice note.
- Kept the FakeDB's `"FROM HANDOFFS"` match broad (any query mentioning that table) rather than pattern-matching the exact SQL text, since `trigger()`'s idempotency SELECT is the only query this pipeline currently issues against `handoffs` — narrower matching would be speculative precision with no test benefit today.

## Deviations from Plan

None — plan executed exactly as written. Every artifact, key link, and test named in the plan's `must_haves` block is present: `tests/conftest.py` patches `handoff` and models `handoffs`/pause-preserving sessions; `load_session()` selects `paused`; `processor.py` has the paused gate, keyword handoff, and `handle_unsupported_media`; `tests/unit/test_processor_safety.py` covers all three trigger paths with 20 tests (well over the plan's 150-line minimum, at 268 lines).

## Issues Encountered
None. All three tasks' `<verify>` commands passed on the first attempt; the full suite went from the 431-passed/3-skipped baseline to 451 passed/3 skipped (431 + 20 new tests, zero regressions) after each task and again at the end.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- `_open_handoff()`, `HANDOFF_ACK_REPLY`, and the exact gate ordering inside `handle_message()` are ready for 03-05 to extend: AI-failure handling (making `ai_service.AIUnavailableError` — landed by 03-03 — trigger a handoff instead of just the generic fallback) and tool-call escalation (wiring `policy.validate()`'s denials, and the `request_human_handoff` tool from 03-03, into `_make_tool_executor`) both slot into the same function this plan already touched.
- `tests/conftest.py`'s shared `mock_db` patch list now covers every seam 03-05's new handoff call sites will need — no further conftest changes should be required for that plan's own tests to stay isolated from the live database.
- No blockers. `app/routers/whatsapp.py` was correctly left untouched (verified via `git diff --stat` against the pre-plan commit) — all bot logic remains centralized in `processor.py` as the architecture requires.

---
*Phase: 03-agent-dependability-safety*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: tests/unit/test_processor_safety.py
- FOUND: tests/conftest.py
- FOUND: app/routers/whatsapp_helpers.py
- FOUND: app/services/processor.py
- FOUND: .planning/phases/03-agent-dependability-safety/03-04-SUMMARY.md
- FOUND commit 63cade3 (Task 1: test(03-04))
- FOUND commit 90e74fb (Task 2: feat(03-04))
- FOUND commit 78e15ce (Task 3: feat(03-04))
