# Agent Safety

**Summary**: How ALYASMEEN's WhatsApp bot stays safe with no human in the loop by default —
a deterministic policy gate in front of every AI tool call, and a durable handoff system
that mutes the bot and calls a human when the conversation needs one. Built in Phase 3
(agent-dependability-safety), on top of Phase 4's outbox and Phase 5's handoff read/resolve
paths.

**Sources**: app/services/policy.py, app/services/handoff.py, app/services/processor.py,
app/services/ai_service.py, app/services/audit.py, app/worker.py,
tests/unit/test_phase3_requirements.py, tests/unit/test_policy.py,
tests/unit/test_processor_policy.py, tests/unit/test_handoff_trigger.py

**Graph**: no matching graphify community — the last graph sync (`raw/graphify-report-snapshot.md`)
is dated 2026-06-14, before `policy.py`, `handoff.py`, or any of Phase 3/4/5 existed. Re-run
graphify and re-sync `graph/graph-overview.md` before trusting the graph layer for this area.

**Last updated**: 2026-08-28

---

> **Sibling pages are stale.** [[whatsapp-bot-brain]] and [[ai-service]] both predate the
> 2026-08-25 `processor.py` rewrite and the outbox/policy-gate/handoff architecture described
> below — neither mentions `processor.py`, `gatekeeper.py`, `policy.py`, `handoff.py`, or
> `audit.py`. `log.md`'s 2026-08-25 entries already flag this ("need a review pass"); it
> remains real, unpaid debt as of this page. Do not treat those two pages as current for
> anything about how a message is actually handled — this page and [[scheduler-jobs]] (also
> due for a pass) are the only ones verified against the current code as of 2026-08-28.

## Why this exists

The bot answers real customers in Arabic with no human reading every message first. Two
independent, deterministic mechanisms keep that safe without relying on the AI to police
itself: a **policy gate** that runs *before* any AI-proposed tool call is allowed to execute
(app/services/policy.py), and a durable **handoff** system that mutes the bot and pages the
aunt over WhatsApp the moment a conversation looks like it needs a human
(app/services/handoff.py, app/services/processor.py). Both are pure/DB-bound Python — no
extra network calls, because `app/worker.py`'s `BlockingScheduler` polls every 2-3 seconds
and cannot tolerate blocking work in the message path (source: app/worker.py:36-37).

## The policy gate

`app/services/policy.py` performs **no I/O at all** — no DB import, no AI call, no network
(source: app/services/policy.py:9-19). Every value it needs — the catalog, whether the
session is paused, an order-status lookup — arrives through the `context` dict the caller
(`processor.py`) already has in hand, rather than the module reaching out and fetching it
itself. This is deliberate, for two reasons the module's own docstring gives: it keeps the
gate genuinely deterministic and trivially unit-testable, and this codebase binds DB helpers
at import time — a `catalog` imported inside `policy.py` would become one more seam every
future test file has to remember to patch, or silently hit the live production database
(source: app/services/policy.py:9-19; see tests/conftest.py's module docstring for the same
warning about `app.services.handoff`).

`validate(tool_name, args, context) -> PolicyDecision` (source: app/services/policy.py:196-249)
runs a fixed rule order, first denial wins:

1. `session_paused` — a human already owns this conversation.
2. `unknown_tool` — default-deny; an unrecognised tool name is either a hallucination or a
   new tool nobody updated this file for. Denying by default (rather than allowing by
   omission) is the point.
3. `order_not_mutable` — unreachable with today's five tools (none has scope `"order"` in
   `TOOL_SCOPES`) but present so a future order-scoped tool is refused unless the order is
   still `to_do`.
4. Per-tool argument rules (`_ARG_VALIDATORS`) — catalog grounding for `add_to_cart`, quantity
   clamping (`MIN_CART_QTY`/`MAX_CART_QTY`, 1-50), address length for `save_address`, reason
   truncation for `request_human_handoff`.

`PolicyDecision` (source: app/services/policy.py:74-81) carries `allowed`, a machine `code`,
an Arabic `message` handed back to Claude as the tool result (so the customer sees a natural
sentence, not an error code), normalised `args` to actually execute with, and `escalate` — a
denial that should also open a handoff (today only `unknown_tool` sets this).

`TOOL_SCOPES` (source: app/services/policy.py:56-62) maps every one of the 5 AI tools to
what it's allowed to touch (`read`, `cart`, `customer`, `escalation`) — `"order"` has zero
members by design: order creation only ever happens through the hard-coded `confirm` command,
never through a tool, and no tool progresses an order's status at all. See
[[#The order-mutation boundary]] below.

`detect_handoff_keyword(text) -> str | None` (source: app/services/policy.py:321-336) is the
separate, purely deterministic keyword/phrase matcher used *before* any AI call — see
[[#The handoff triggers]].

## The handoff triggers

Five reason codes open a handoff via `handoff.trigger(phone, reason, metadata)`
(source: app/services/handoff.py:115-183), each fired from a different point in the pipeline:

| Reason code | Fires in | What it detects |
|---|---|---|
| `keyword_request` | `processor.handle_message`, before hard commands (source: app/services/processor.py:358-374) | `policy.detect_handoff_keyword()` matched an explicit "talk to a human" / complaint / refund / damaged-item / privacy phrase |
| `unsupported_media` | `processor.handle_unsupported_media`, called from `process_event`'s non-text/interactive branch (source: app/services/processor.py:242-246, 496-529) | A voice note, image, sticker, document, video, location, or contacts message the bot cannot read |
| `ai_failure` | `processor.handle_message`'s `except` blocks around `generate_reply()` (source: app/services/processor.py:445-463) | `AIUnavailableError` (or any other exception) — a real Claude/API outage, not a normal reply |
| `ai_requested` | `processor._tool_request_human_handoff`, dispatched from the policy-gated tool executor (source: app/services/processor.py:694-708, 587-588) | Claude itself called `request_human_handoff` — escalation rules live in the system prompt (source: app/services/ai_service.py:184-189) |
| `policy_denied` | `_make_tool_executor`'s closure, when a denial has `decision.escalate = True` (source: app/services/processor.py:561-571) | Today only an `unknown_tool` denial escalates; per-tool argument denials (bad address, product not found) do not — those are ordinary conversational corrections |

Two of these — `keyword_request` and `ai_requested` — are worth contrasting: the keyword path
is pure string matching with zero AI involvement (cheap, deterministic, catches explicit
phrasing); the tool path relies on Claude's own judgment for cases the dataset shows are
sentiment/context-driven, not vocabulary-driven (an angry customer rarely says the word
"human"). Both are needed — see `.planning/phases/03-agent-dependability-safety/03-RESEARCH.md`'s
handoff-signal-design section for the dataset analysis behind this split.

**A sixth reason code, `operator_takeover`,** exists in `REASON_LABELS`
(source: app/services/handoff.py:39-46) but is unrelated to this phase's message pipeline —
it is written by `app/routers/ui_api.py`'s `api_update_status` when an operator forces a
status change while the bot is still active on that conversation (Phase 5, plan 05-06).

### The paused gate — what makes every trigger stick

`handle_message`'s very first check, before any hard command or the AI fallback, is
`if st.get("paused"):` (source: app/services/processor.py:353-356) — record what the customer
said (so the transcript is complete when the aunt opens it), send nothing, return. This is
not itself a trigger; it is what stops the bot from talking over a human once any of the five
triggers above has fired, and it is why `handoff.trigger()`'s per-phone idempotency
(re-asserting the pause rather than opening a second row on a repeat call, source:
app/services/handoff.py:148-159) is enough to guarantee **at most one handoff and one aunt
notification per customer per incident** — a second angry message, or a second voice note,
during an already-open handoff produces neither a duplicate row nor a duplicate alert.

## The handoff lifecycle

```
trigger()  (Phase 3, app/services/handoff.py:115-183)
    │  1. idempotency check — reuse an active handoff for this phone if one exists
    │  2. INSERT INTO handoffs (status='active')
    │  3. _pause_session() — UPSERT sessions.paused = TRUE (not a bare UPDATE — the
    │     very first message from a brand-new customer may itself be the trigger,
    │     before any sessions row exists; source: app/services/handoff.py:186-201)
    │  4. audit.log_action("bot", "handoff_triggered", ...) — best-effort
    │  5. _notify_aunt() — plain-Arabic WhatsApp alert via processor.queue_text
    │     (the durable outbox, never a direct send; source: app/services/handoff.py:204-240)
    ▼
the aunt reads the alert, opens the "محادثات" dashboard tab, replies by hand
    ▼
resolve(handoff_id, resolved_by)  (Phase 5, app/services/handoff.py:49-77)
    │  1. UPDATE handoffs SET status = 'resolved' (idempotent — a no-op on an
    │     already-resolved or nonexistent id, returns False)
    │  2. UPDATE sessions SET paused = FALSE  (a BARE update is safe here — a
    │     session row provably exists by the time a handoff is ever resolved)
    │  3. audit.log_action(resolved_by, "handoff_resolved", ...)
```

The asymmetry in step 3 (`trigger()` UPSERTs, `resolve()` UPDATEs) is intentional and
documented at the source, not an inconsistency — see the citation above.

## The order-mutation boundary

The agent can create an order only through the hard-coded `confirm`/`تأكيد` command path
(`processor._handle_confirm` → the `create_order_atomic` RPC, source:
app/services/processor.py:745-796) — never through any AI tool, and always landing the new
order in `to_do`. It can never change an order's status at all: only
`app/routers/ui_api.py`'s operator-authenticated `api_update_status` issues
`UPDATE orders SET status` (source: app/routers/ui_api.py:148,160,168). This has been true by
construction since before Phase 3 (no tool ever had a status-mutating argument), but was
previously an architectural fact held up by convention alone, not a regression-tested one.
`tests/unit/test_phase3_requirements.py::TestAgentCannotMutateOrders` now pins it at three
independent layers — the AI tool surface (no tool name/property implies mutation), the
`policy.TOOL_SCOPES` map (every tool has a scope, `"order"` has no members), and a
source-level AST guard (the `UPDATE orders SET status` string appears only in `ui_api.py`;
the `create_order_atomic` RPC call appears only inside `processor._handle_confirm`, nowhere
else in `processor.py`, `ai_service.py`, or `policy.py`). If either boundary legitimately
needs to change, that test and this section must be updated together — see the test's own
docstring.

## The eval gate

Before any change that touches the agent's message-handling code ships, the release process
described in `docs/EVAL_GATE.md` (plan 03-07) is meant to run — a bounded, cost-controlled
pytest suite (`tests/eval/`, opt-in via `RUN_AGENT_EVAL=1`) that drives the real
`handle_message()` pipeline over the 75-case labeled dataset
(`tests/data/whatsapp_agent_dataset.json`) and compares against a measured baseline
(`.planning/phases/03-agent-dependability-safety/03-EVAL-BASELINE.md`: 85.1% overall,
75.0% critical, 68.8% handoff, 100% informational, measured 2026-08-28). This page
deliberately does not restate the pass/fail thresholds themselves — `docs/EVAL_GATE.md` is
the single source for those; check there, not here, before relying on a specific number.

## Gotchas for the next session

- **`tests/conftest.py`'s autouse `mock_db` fixture patches modules by name**, not by
  scanning for DB usage — `app.services.handoff` was added to that patch list in plan 03-04,
  `app.services.audit` in plan 05-09. A new module that calls `query`/`execute` and is
  exercised by a test driving `handle_message()`/`process_webhook_events()` end-to-end must be
  added to that same list, or the test either fails loudly against `block_live_db` or —
  worse, if `ALLOW_LIVE_DB=1` is ever set — actually writes to production. This has already
  happened twice in this repo's history (source: tests/conftest.py's own `block_live_db`
  docstring).
- **A new audit action string must be added to `OPERATOR_ACTIONS`**
  (source: app/services/audit.py:24-32) or `list_operator_actions()` — and therefore the
  `/audit` dashboard page — silently excludes it. `audit.log_action()` still writes the row
  either way (the allowlist only governs reads), so the failure mode is invisibility, not an
  error.
- **`policy.py` needs no patching in tests, ever** — it performs no I/O by design (see
  [[#The policy gate]] above). If a future change makes it import `app.db.database` or any DB
  helper, that is itself a design regression worth pushing back on, not just a missing test
  patch.
- **Never add blocking work to the `handle_message`/tool-executor path.** `app/worker.py`
  runs a single-threaded `BlockingScheduler` polling every 2-3 seconds
  (source: app/worker.py:36-37); `app/shared/gatekeeper.py`'s module docstring documents a
  prior incident where an unbounded sleep in this path stalled the whole worker. Any new
  validation/detection logic here must stay DB-bound (already circuit-breaker-protected via
  `app/db/database.py`) or pure Python.

## Related pages

- [[whatsapp-bot-brain]] (stale — see the note at the top of this page)
- [[ai-service]] (stale — see the note at the top of this page)
- [[scheduler-jobs]] (due for a review pass against the outbox rewrite)
- [[database-tables]]
- [[design-decisions]]
- [[alyasmeen-auntops]]
