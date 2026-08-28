# Phase 3: Agent Dependability & Safety - Research

**Researched:** 2026-08-28
**Domain:** Deterministic policy gating + human handoff + AI eval-gate, layered onto an existing durable-outbox WhatsApp bot
**Confidence:** HIGH (current-code claims — verified by direct file reads) / MEDIUM (eval-gate design — no precedent in this repo to copy)

## Summary

Phase 3 does **not** start from a blank slate. Three things it needs already exist and are
explicitly reserved for it: the `sessions.paused` column (live), the `handoffs` +
`audit_logs` tables (live), and `app/services/handoff.py` (built by Phase 5, but its own
module docstring explicitly refuses to implement `trigger()`/keyword-detection/policy-gate
— "belong to Phase 3 ... and must be added there when that phase runs, not duplicated
here"). What's missing is the **producer** side: nothing in the current message pipeline
ever calls `handoff.trigger()`, checks `sessions.paused`, or validates a tool call before
it runs. `app/routers/whatsapp.py` is a thin webhook receiver only (persists to
`webhook_events`); the entire bot brain — hard commands, session state machine, the 2-call
agentic AI loop, and all 4 tool executions — lives in `app/services/processor.py`,
polled by `app/worker.py` every 2-3s. This is the one file both a policy gate and a handoff
trigger must integrate into.

The three stale plans (`03-01/02/03-PLAN.md`) got the *shape* of the work right — policy
engine, handoff service, eval script, hard fallback — but were written before the
2026-08-25 hardening session moved the bot brain from `whatsapp.py` into `processor.py`,
before Phase 4's outbox/gatekeeper rewrite, and before Phase 5 built half of
`handoff.py` and the operator UI that already consumes it. Concretely: Task 1 of 03-01
(add the `paused` column) is **already done** — don't redo it. Task 3 of 03-01
(`HandoffService`) is **half-built** — `resolve()`/`active_count()`/`bot_recently_active()`
exist; only `trigger()` is missing, and it must follow the exact query/execute/audit
pattern `resolve()` already established. Task 2 of 03-03 (hard-coded AI fallback) is
**already done** in `processor.py`, but is close to unreachable dead code because
`ai_service.generate_reply()` already catches every exception internally and always
returns a string — the planner needs to decide whether to let a distinguishable failure
propagate so a handoff can actually fire on AI outage. Task 1 of 03-03 (eval script)
overlaps with an already-existing, more mature (but non-pytest, real-API-calling) script,
`tests/data/eval_intent.py`, plus a already-generated 56,000-row noisy dataset — but
neither of those satisfies REQ-prod-eval-gate's "pytest-based ... release gate" literally,
and this repo has **no CI** to hook a gate into at all.

**Primary recommendation:** Build a `handoff.trigger()` in `app/services/handoff.py`
(mirroring `resolve()`'s query/execute/audit pattern) and a thin, deterministic policy
layer inline in — or as a small new module called from — `processor.py`'s
`_make_tool_executor()`/`handle_message()`, wired at exactly the three points the
current architecture already exposes: (1) a `paused`-session check added to the top of
`handle_message` (currently absent — `load_session()` doesn't even `SELECT` the column),
(2) a keyword/media/tool-failure handoff trigger inside `handle_message` and
`process_event`, and (3) a pytest-marked, opt-in eval-gate test file under `tests/` that
runs a bounded sample of the existing 75-case dataset through the real `handle_message`
pipeline (not a separate classification prompt) and asserts thresholds, reusing the
`integration` marker convention already in `pyproject.toml` to keep it out of the default
`pytest` run.

## Current Message Flow (verified, file:line)

```
Meta webhook (real) / mock sender (dev, USE_MOCK_WHATSAPP=1)
        │
   POST /whatsapp/webhook                         app/routers/whatsapp.py:31-104
        │  1. HMAC verify (verify_signature)                      :40-42
        │  2. Parse Meta payload defensively                      :59-86
        │  3. INSERT INTO webhook_events (processed=FALSE)        :91-94
        │  returns {"status": "received"} immediately — no reply is
        │  computed synchronously here at all.
        ▼
app/worker.py — BlockingScheduler, "webhook_processor" job, every 3s   app/worker.py:37
        │
   process_webhook_events()                        app/services/processor.py:136-171
        │  SELECT ... FROM webhook_events WHERE processed=FALSE LIMIT 10   :138-140
        │  per event: attempts+=1, then process_event(id, phone, payload)  :146-154
        │  on exception: retry up to MAX_WEBHOOK_EVENT_ATTEMPTS=3 (line 36),
        │  then dead-letter (processed=TRUE, error="dead-letter: ...") and
        │  notify_permanent_failure("webhook_event", ...)                  :157-166
        ▼
   process_event(event_id, phone, payload)          app/services/processor.py:198-238
        │  extracts entry[0].changes[0].value.messages[0]                  :202-213
        │  msg_type == "text"        -> handle_message(phone, text, name)  :214-217
        │  msg_type == "interactive" -> button_reply id -> handle_message  :218-223
        │  ELSE (audio/image/sticker/document/location/...): SILENTLY
        │  IGNORED — no branch exists for any other msg_type. Event is
        │  still marked processed=TRUE at the end (line 235-238) with NO
        │  reply and NO handoff. <- Phase 3 gap (research focus #1/#3).
        │  statuses (read receipts) are logged only, line 226-228.
        ▼
   handle_message(phone, text, name)                app/services/processor.py:296-386
        │  1. upsert_customer, get_customer_name                          :299-300
        │  2. st = load_session(phone)  — NOTE: does NOT select `paused`,
        │     see app/routers/whatsapp_helpers.py:54-68. There is currently
        │     NO code path anywhere that reads sessions.paused during
        │     message handling. <- Phase 3 gap (research focus #1).
        │  3. Hard commands (menu/cart/clear/confirm/pickup/delivery,
        │     Arabic variants, numeric menu picks)                        :310-363
        │  4. Fallback to AI: append_history, then
        │     tool_executor = _make_tool_executor(phone, st, cart)        :368
        │     reply = generate_reply(..., tool_executor=tool_executor)    :371-380
        │     (wrapped in try/except -> AI_FALLBACK_REPLY, see below)
        │  5. append_history(assistant), queue_text(phone, reply), save_session
        ▼
   _make_tool_executor(phone, st, cart)              app/services/processor.py:393-411
        │  closure; dispatches by tool name to _tool_add_to_cart /
        │  _tool_show_menu / _tool_get_order_status / _tool_save_address.
        │  <- Phase 3's policy-gate integration point (research focus #2):
        │  currently NO validation layer wraps this dispatch at all.
        ▼
generate_reply(...)                                 app/services/ai_service.py:336-446
        │  builds system prompt + full <catalog> block + cart + knowledge,
        │  calls Claude via gatekeeper.execute("claude_ai", ...)          :402
        │  if stop_reason == "tool_use": executes tool_executor per block,
        │  catches tool_executor exceptions ITSELF and turns them into a
        │  tool_result string (never raises out)                         :408-423
        │  second call forces tool_choice="none" for the final text reply :429-436
        │  the WHOLE function is wrapped in try/except returning a
        │  hard-coded Arabic string on ANY exception, including
        │  Anthropic API errors — this function effectively NEVER raises. :444-446
```

Reply delivery is a second, independent poll loop — `handle_message` never calls
`send_text`/`send_buttons` directly:

```
processor.queue_text(phone, text) / queue_buttons(...)   app/services/processor.py:56-69
        │  INSERT INTO outbox_jobs (kind, phone, payload)
        ▼
app/worker.py — "outbox_processor" job, every 2s          app/worker.py:38
        │
   process_outbox_jobs() -> process_job(...)               app/services/processor.py:174-289
        │  kind='whatsapp_message'|'whatsapp_buttons'|'pdf_invoice'
        │  calls send_text/send_buttons/send_document_bytes directly (the
        │  ONLY place that does, besides scheduler services)
        │  on permanent failure (attempts >= max_attempts): status='failed',
        │  notify_permanent_failure("outbox_job", ...)                    :288-289
```

**Where a policy gate slots in:** `_make_tool_executor`'s `executor(name, args)` closure
(`processor.py:394-409`) is the single chokepoint every AI tool call already passes
through — exactly where the stale `03-02-PLAN.md` said to put it, and that file reference
is still correct today (it was already `processor.py`, not `whatsapp.py`, at the time that
plan was written — this part never went stale).

**Where a handoff trigger slots in:** three natural call sites, matching the phase's own
requirement list — (a) `process_event` for unsupported media types (currently the silent
`else` — no branch exists), (b) `handle_message`'s hard-command / free-text dispatch for
explicit "talk to a human" phrases and detected distress, and (c) inside the
`_make_tool_executor` closure or the AI-failure `except` block in `handle_message` for
tool-call denials / AI outages that should escalate rather than just apologize.

## Existing Building Blocks (don't rebuild these)

### `app/services/handoff.py` — half-built, by design

```python
# app/services/handoff.py:1-13 (module docstring, verbatim)
"""handoff.py — Handoff resolution and read paths (REQ-prod-handoff).

Phase 5 owns handoff *resolution* and read paths only. Creating a handoff,
pausing the session, keyword/media detection, and the policy gate that
decides when a conversation needs a human belong to Phase 3
(`03-01-PLAN.md` / `03-02-PLAN.md`) and must be added there when that phase
runs, not duplicated here. This module deliberately does not define that
entry point — an empty stub that looks implemented would be worse than an
absent one.
"""
```

What exists today (verified, `app/services/handoff.py`):
- `resolve(handoff_id, resolved_by) -> bool` (lines 32-60) — idempotent; sets
  `handoffs.status='resolved'`, `sessions.paused=FALSE`, and calls
  `audit.log_action(resolved_by, "handoff_resolved", {...})` via a **lazy import**
  (`from app.services import audit` inside the function, to avoid an import cycle —
  follow this same lazy-import pattern for `trigger()`).
- `active_count() -> int` (63-66) — powers the dashboard nav badge.
- `bot_recently_active(phone, window_minutes=5) -> dict | None` (69-95) — already used by
  `ui_api.api_update_status` as a bot-vs-operator conflict guard
  (`app/routers/ui_api.py:107-132`); reads `chat_history` for the last assistant
  message and `sessions.paused`. **Not** a lock — a cheap heuristic, by design
  (`CONFLICT_WINDOW_MINUTES` docstring, handoff.py:24-29).

What's missing: `trigger(phone, reason, metadata=None, assigned_to="aunt") -> str|None`
(handoff id). Must, per the module's own contract and the DB constraints already live:
1. `INSERT INTO handoffs (phone, reason, status, assigned_to) VALUES (%s, %s, 'active', %s)`
   — same shape `ui_api.py:126-129` already uses for `operator_takeover` handoffs; `phone`
   has a live FK to `customers(phone)` (`supabase/migrations/20260614000001...sql:48`), so
   the customer row must already exist (it always will — `handle_message` calls
   `upsert_customer` before any handoff-worthy code runs).
2. `UPDATE sessions SET paused = TRUE WHERE phone = %s` — mirrors `resolve()`'s own
   `UPDATE sessions SET paused = FALSE` at line 52, just inverted.
3. `audit.log_action(actor, "handoff_...", {...})` — **note**: `"handoff_triggered"` (or
   whatever action string `trigger()` writes) is **not** in `audit.OPERATOR_ACTIONS`
   (`app/services/audit.py:24-32`, currently only lists `handoff_resolved`). `log_action`
   itself still writes it (best-effort, allowlist only governs reads — audit.py:38-41), but
   `list_operator_actions()` — and therefore the `/audit` dashboard page (05-07) — will
   **silently exclude** it unless the plan adds the new action string to
   `OPERATOR_ACTIONS`. Confirmed load-bearing by STATE.md's own note: "Any plan writing a
   new kind of audit row must add its action string to `OPERATOR_ACTIONS` in
   `app/services/audit.py` first."
4. Idempotency: decide whether re-triggering an already-active handoff for the same phone
   should no-op (like `resolve()` does for already-resolved) or open a second row — there
   is currently no unique constraint preventing multiple active `handoffs` rows for one
   phone (`idx_handoffs_status` is a plain partial index, not unique).

Should `trigger()` also `queue_text(phone, ...)` a confirmation to the customer, and
`queue_text(Config.AUNT_PHONE, ...)` an alert? Both stale plans (03-02 Task 2) and the old
`RESEARCH-3.md` assume yes — and the pattern to reuse is `processor.py`'s own
`notify_permanent_failure()` (lines 93-129): loop-guarded (never alert the aunt/admin about
their own phone), through `queue_text` (the durable outbox), never a direct `send_text`.

### The 4 AI tools already ground themselves — no hallucination vector for products

`_tool_add_to_cart` (`processor.py:414-458`) looks the product up in `catalog()` (which
reads live from Supabase via `app/ai/retriever.py`) and takes its `list_price` from the
catalog row — **the AI-supplied `qty` is clamped (`MIN_CART_QTY=1`, `MAX_CART_QTY=50`,
lines 39-40, 435-441) but price is never taken from the AI's tool-call args at all.**
REQ-ai-no-hallucination's "no price overrides" concern (03-01's Rule 1) is therefore
**already structurally satisfied** by the tool implementation itself — there is no
`price` argument in the `add_to_cart` tool schema (`ai_service.py:225-244`) for the AI to
override in the first place. A formal `policy.py` validate() layer would be reinforcing an
already-enforced invariant here, not fixing a live hole. Where a policy layer *does* add
real value: centralizing/testing this invariant explicitly, validating `save_address`'s
length/shape, and — see below — the order-status boundary.

### There is no AI tool that can mutate order status — success criterion 4 is structural, not enforced

The 4 tools are `add_to_cart`, `show_menu`, `get_order_status` (read-only), `save_address`
(`ai_service.py:212-306`). None of them write to `orders.status`. Order **creation**
(initial `status='to_do'`) happens only through the hard-coded `confirm`/`تأكيد` command
path (`processor.py:327-329` -> `_handle_confirm` -> `rpc("create_order_atomic", ...)`,
lines 545-596) — never through the AI/tool path. Status **progression**
(`to_do -> ready -> delivered -> done`) happens exclusively in
`app/routers/ui_api.py`'s `api_update_status` (operator-authenticated dashboard endpoint,
`require_operator` dependency), which the bot/AI never calls. So "automated `to_do` order
changes work reliably while later statuses block agent mutation" (Success Criterion 4) is
**already true by construction** today — there is no code path for the AI to violate it.
What Phase 3 should decide: does REQ-prod-policy-gate want this documented/tested as an
explicit, asserted invariant (e.g. a unit test asserting the tool list contains no
status-mutating tool, or a policy-layer allowlist that would reject one if a future tool
tried), or is "no such tool exists" sufficient? Recommend the former — cheap, and it turns
an implicit architectural fact into a regression-tested one before any future tool is added
carelessly.

### `queue_text`/durable outbox already covers REQ-bot-aunt-notification and REQ-sched-followup

- New-order aunt notification: `_handle_confirm` -> `queue_text(Config.AUNT_PHONE, ...)`
  (`processor.py:589-590`) — goes through the same durable outbox as customer messages,
  so a WhatsApp API failure retries via `process_outbox_jobs` instead of silently dropping
  (unlike the project CLAUDE.md's description of a bare try/except send — that description
  is stale; the outbox now provides the retry).
- Follow-ups: `app/services/followup.py:61` calls `queue_text` too (not a direct send).
- **retry_queue.py is retired** (Phase 4, migration `20260825000003_retire_retry_queue.sql`)
  — REQ-sched-retry-queue is satisfied by the outbox_jobs/poller architecture already in
  place. Verify only; do not rebuild a retry mechanism.

### AI-failure fallback already exists, but is close to unreachable — a real design gap

`processor.py:370-380`:
```python
try:
    reply = generate_reply(
        user_message=text, previous_messages=history, cart=cart,
        customer_name=customer_name, tool_executor=tool_executor
    )
except Exception as e:
    log.error("ai_reply_failed", error=str(e), phone=phone)
    reply = AI_FALLBACK_REPLY   # "عذرًا، في مشكلة تقنية مؤقتة، جرب كمان شوي 🙏"
```
This satisfies 03-03's Task 2 goal already — **but** `ai_service.generate_reply()`
(`ai_service.py:388-446`) wraps its *entire* body (the Anthropic call, the tool-execution
loop, everything) in its own try/except that always returns a string
(`"عذرًا، صار خلل مؤقت. جرّب مرة ثانية 🙏"`, line 446) and **never re-raises**. Tool-executor
exceptions are caught even one layer deeper, inside the agentic loop itself
(`ai_service.py:412-416`), and turned into a `tool_result` string Claude then talks around.
The practical result: `processor.py`'s own `except` block is reachable only if something
monkeypatches or replaces `generate_reply` itself (which is exactly what
`tests/unit/test_processor.py:335-346`'s `test_ai_failure_sends_fallback_instead_of_raising`
does) — in production, a real Claude timeout/rate-limit/API error is swallowed *inside*
`ai_service.py` and comes back as `ai_service.py`'s own Arabic fallback string, indistinguishable
from a normal reply. **This means "AI failure produces a handoff" (implied by both stale
plans) currently has no trigger point that can ever fire in production.** The planner needs
one of: (a) have `ai_service.py` raise a distinguishable exception type on real failures
(breaks its "always returns a string" contract, touches the one-AI-file rule's boundary
carefully), (b) have `processor.py` string-compare the reply against `ai_service.py`'s two
known fallback constants (fragile — two near-duplicate Arabic strings already exist,
`processor.AI_FALLBACK_REPLY` and `ai_service`'s inline one, which is itself worth
consolidating), or (c) decide AI-failure handoff is out of scope for this phase and rely on
`gatekeeper`'s rate-limit logging + the existing fallback text alone. This is a genuine open
question, not a solved one — flag prominently for the planner.

### `gatekeeper.py` is synchronous by hard design — do not add blocking work to the tool/AI path

`app/shared/gatekeeper.py`'s module docstring (lines 1-27) explains at length why it is
fully synchronous with a small bounded wait (`_MAX_WAIT_SECONDS = 1.5`, line 48) and no
internal retry loop: the worker is a `BlockingScheduler` with 2-3s job intervals and
`max_instances=1` — any code added to the `handle_message`/tool-executor path that blocks
or sleeps meaningfully will cause skipped poll ticks. A policy gate or handoff trigger added
here must stay purely synchronous, DB-bound (already the pattern everywhere else in this
codebase), and must not add network calls beyond the existing `query`/`execute`/`rpc` seam.

## Handoff Trigger Signal Design — grounded in the existing 75-case eval dataset

`tests/data/whatsapp_agent_dataset.json` (75 entries: `id`, `raw_input`, `expected_intent`,
`language_profile`, `entities`, `edge_case_tags` — no `expected_tool`/`expected_handoff`
field) already contains curated examples that map almost one-to-one onto the handoff
signals research focus #3 asked about. Verified entries (id | intent | raw_input | tags):

| id | expected_intent | raw_input (paraphrased sense) | edge_case_tags |
|----|------------------|-------------------------------|-----------------|
| 45 | `request_human_handoff` | "Can I talk to Hanan herself, not the bot, I have something private" | `human_handoff_trigger`, `privacy_sensitive_topic` |
| 57 | `track_order_with_refund_threat` | Angry — "3 days of 'tomorrow tomorrow', give my money back" | `angry_customer`, `refund_request`, `de_escalation_required` |
| 35 | `track_order_with_complaint` | "My order's been a week, nobody answered" | `complaint_escalation`, `negative_sentiment` |
| 23 | `report_damaged_item_and_request_resolution` | Cream jar arrived broken | `customer_complaint`, `refund_or_replacement_trigger` |
| 47 | `unsupported_media_voice_note` | `[رسالة صوتية - 0:43]` | `unsupported_media`, `agent_should_ask_for_text` |
| 67 | `unsupported_media_sticker` | `[ملصق]` | `unsupported_media`, `should_not_trigger_tools` |
| 63 | `privacy_concern` | "Who are you, how did you get my number, I never signed up" | `privacy_complaint`, `compliance_sensitive` |
| 54 | `opt_out_of_messages` | "Stop sending me messages, I don't want anything" | `opt_out_request`, `compliance_sensitive` |
| 29 | `duplicate_third_party_order` | "Same order as my sister ordered last week, repeat it for me" | `cross_user_reference`, `privacy_check_trigger` |
| 55 | `wrong_recipient` | Message clearly meant for a grocer, not this bot | `wrong_number`, `out_of_catalog_products` |

Design implication: a **keyword list alone** (the stale 03-02 plan's suggestion —
`"human", "agent", "حنان", "تحويل"`) would catch id 45 but miss 57, 35, 23, 63 entirely —
none of those contain an explicit "give me a human" phrase; they're detected by
**sentiment/intent**, not vocabulary. Recommend three independent trigger classes, matching
what the current architecture can actually detect deterministically vs. what needs the AI's
own judgment:
1. **Deterministic, pre-AI (in `handle_message`, before the AI call):** explicit keyword
   match (extend the 4-word list using dataset-derived phrases) + unsupported media
   (`process_event`, msg_type not in {text, interactive}) — cheap, no API call needed, and
   this is the one class the stale plans already scoped correctly.
   `opt_out_of_messages` (id 54) is arguably **not** a handoff case — it's a
   do-not-message/consent-suppression concern (no such mechanism exists in this codebase
   at all today) and conflating it with human-handoff would mis-route a compliance issue
   into the aunt's WhatsApp inbox instead of suppressing outbound sends. Flag as a scope
   decision, not an oversight.
2. **AI-detected, via a tool call:** add a `request_human_handoff` tool (5th tool) that
   Claude calls when it judges the customer wants/needs an escalation (angry tone, refund
   demand, privacy complaint) — mirrors the old `RESEARCH-3.md`'s "Ghost Cancellations"
   pitfall warning (don't let Claude claim "I've escalated this" in prose without an actual
   tool call backing it) and gives deterministic backing (a real DB write) to what would
   otherwise be a purely linguistic judgment.
3. **System-triggered, no AI involved:** tool-call validation failure from the policy layer,
   and (per the AI-failure discussion above) a real AI/API failure once that path is made
   distinguishable.

## Eval-Gate Design (REQ-prod-eval-gate)

### What already exists

`tests/data/eval_intent.py` (not pytest, git-tracked, `tests/data/`) is a mature,
already-working standalone script:
- Loads a companion 56,000-row noisy dataset, `tests/data/whatsapp_agent_dataset_noisy.json`
  (**75 MB, already generated and git-tracked** — `git ls-files` confirms), produced by
  `tests/data/generate_noise_dataset.py` from the base 75 examples across 8 noise levels
  (10%-80% character corruption).
- Calls the **real** Claude API directly (`Anthropic(api_key=...)`, no gatekeeper, no mock)
  with a bespoke intent-classification system prompt (`CLASSIFY_SYSTEM`,
  `eval_intent.py:116-122`) — **not** the actual bot pipeline. It measures "can Haiku
  classify a noisy message's intent," not "does `handle_message` do the right thing."
- Has a defined `VALID_INTENTS` list (63 values) and `NEAR_MISS_GROUPS` for partial credit,
  cost estimates in its own docstring (~$0.05 for a 240-call quick run), and a
  `--samples`/`--levels`/`--out` CLI.

This is valuable prior art but **does not satisfy REQ-prod-eval-gate literally**: it is not
pytest, has no pass/fail threshold/gate semantics (it prints a report), and evaluates a
side-channel classification prompt rather than the production `generate_reply`/
`handle_message` code path (so it cannot catch e.g. a tool-call regression, a policy-gate
false-positive, or a handoff that fails to fire).

### What REQ-prod-eval-gate needs that doesn't exist

1. **A pytest-based test** (not a standalone script) so it can be invoked with
   `pytest tests/eval/...` and produce a normal pass/fail exit code — the literal ask.
2. **Driven through the real pipeline**, not a side prompt — i.e. call
   `app.services.processor.handle_message()` (or `generate_reply()` directly for a
   lighter/cheaper variant) for each dataset case and assert on the *outcome* (which tool
   fired, whether a handoff was triggered, whether the reply stayed in the customer's
   language) rather than a separately-elicited intent label.
3. **A mapping from `expected_intent`/`edge_case_tags` to expected *behavior*** — this does
   not exist today. `expected_intent` values (`add_to_cart`-worthy: `create_order`,
   `select_menu_item*`, `update_cart_quantity`; handoff-worthy: `request_human_handoff`,
   `track_order_with_refund_threat`, `report_damaged_item_and_request_resolution`,
   `unsupported_media_*`; read-only: `track_order_and_request_courier_contact`, etc.) would
   need a small curated lookup table authored as part of this phase — 75 rows is
   small enough to hand-classify once.
4. **Cost control + opt-in gating**, since every case is a real Claude API call. This repo
   already has the exact mechanism needed and unused for this purpose:
   `pyproject.toml`'s `[tool.pytest.ini_options]` defines
   `addopts = '-m "not integration"'` and a registered `integration` marker
   ("marks tests that hit real external services (use with caution)") — the default
   `pytest` run (and presumably any future CI) already excludes anything so marked.
   Marking the eval-gate test(s) `@pytest.mark.integration` keeps them out of the fast,
   free, always-mocked suite (353 passed/3 skipped per STATE.md) and makes them an
   explicit, deliberate `pytest -m integration tests/eval/` invocation — consistent with
   this repo's only other real-API-calling scripts (`eval_intent.py`, ungated, standalone).
5. **No CI exists in this repo** (`.github/` is absent). "How it runs in CI vs locally"
   (research focus #4) has no existing target — recommend the plan document a manual
   pre-release command (e.g. in a `docs/` file or the plan's own verification section)
   rather than assume/build a GitHub Actions workflow, unless the phase's scope is
   explicitly widened to include one.
6. **Sampling, not all 75 cases on every run**, is the sane default given real API cost —
   reuse `eval_intent.py`'s `--samples`/`--seed` pattern for a bounded, reproducible subset,
   with the full 75 (or the noisy 56k) reserved for a manual/periodic deeper run.

### Suggested threshold shape (not verified against any external standard — a starting
proposal for the planner, adapted from the stale `RESEARCH-3.md`'s numbers which were
themselves unvalidated assumptions)

| Tier | Example intents | Suggested threshold |
|------|------------------|----------------------|
| Critical path (cart/menu/confirm tool calls) | `create_order`, `select_menu_item*`, `update_cart_quantity` | High — wrong tool choice here directly breaks an order |
| Handoff-worthy | `request_human_handoff`, `track_order_with_refund_threat`, `unsupported_media_*` | High — a missed handoff means an angry customer talks to a bot that can't help |
| FAQ / informational | `check_product_ingredients`, `request_store_info`, `check_payment_methods` | Lower — a slightly-off answer here is not order-breaking, and today's `app/data/knowledge/` folder is still empty (per `ALYASMEEN/wiki/ai-service.md`), so these will score poorly until that content exists — not a Phase 3 problem to fix, but don't let a naive "one global threshold" gate block on it |

These numbers are **not sourced from anything authoritative** — no external benchmark, no
prior measured baseline in this repo (no eval has ever actually been run against
`handle_message`, only the side-channel `eval_intent.py`). Treat as LOW confidence /
a proposal to validate empirically once the eval-gate exists, not a target to hit blindly.

## Critical Test-Convention Gotcha (verified, will break tests if missed)

`tests/conftest.py`'s autouse `mock_db` fixture (lines 300-338) patches `query`/`execute`
only on **`app.routers.whatsapp_helpers`, `app.services.processor`, and
`app.services.audit`** (the `for mod in (wh, processor, audit):` loop, line 329) — plus
`app.routers.whatsapp` separately (line 333) and `processor.rpc`/`send_text`/`send_buttons`
(lines 334-336). **`app.services.handoff` is not in that list.** Today this is fine because
nothing calls into `handoff.py` from the `processor`/webhook pipeline yet — the one
existing test file for it, `tests/unit/test_handoff_resolve.py`, patches
`handoff.query`/`handoff.execute` itself, locally (its own `fake_handoff_db` fixture,
lines 82-93), and `operator_api.py`'s routes go through `require_operator` +
`FakeDB`-backed `query` already patched elsewhere for those specific test files.

**The moment this phase adds `handoff.trigger()` and calls it from `processor.handle_message`
or `process_event`, any *integration* test that drives a full message through
`handle_message()`/`process_webhook_events()` without an explicit local patch on
`app.services.handoff` will hit the `block_live_db` guard fixture and fail loudly** (or,
worse if `ALLOW_LIVE_DB=1` is ever set, actually write to the live production `handoffs`/
`sessions`/`audit_logs` tables — this has already happened twice in this repo's history per
`tests/conftest.py`'s own `block_live_db` docstring, both during Phase 5). The plan should
explicitly add `handoff` to conftest's shared `mock_db` patch list (same treatment `audit`
already got in 05-09, for the identical reason) rather than leaving every future test file
to remember its own patch.

## Reconciling the Three Stale Plans (explicit intent-vs-reality table)

| Plan | Task | Stale-plan intent | Current reality | Verdict |
|------|------|--------------------|------------------|---------|
| 03-01 | 1: add `sessions.paused` migration | New migration `20260615000000_add_paused_to_sessions.sql` | **Already applied, live** (Phase 1 baseline; column exists, `app/db/schema.sql:63`) | Done — do not redo. Just start reading/using the column. |
| 03-01 | 2: `app/services/policy.py` `PolicyEngine.validate()` | Deterministic rules: no price override, order-status-based tool blocking | `add_to_cart` never accepts a price arg at all (already safe); no tool touches order status (nothing to block) | Design intent still reasonable for centralizing/testing the invariant, but the "Rule 3" example (block tool calls for delivered/done orders) doesn't map onto any real tool — needs rethinking against the actual 4 tools, not invented ones |
| 03-01 | 3: `app/services/handoff.py` `HandoffService.trigger()` | New file, new class | **File exists**; `resolve()`/`active_count()`/`bot_recently_active()` already built (Phase 5); `trigger()` explicitly left out, by the file's own docstring, for this phase | Still valid intent — just append `trigger()` to the existing module using its established query/execute/audit pattern, not a new `HandoffService` class from scratch |
| 03-02 | 1: integrate policy gate into `_make_tool_executor` in `processor.py` | — | File/function reference is **already correct** — `processor.py:393-411` is exactly this closure today | Still valid, unchanged |
| 03-02 | 2: `paused` check + keyword handoff trigger in `handle_message` | 4-word keyword list | `handle_message` has **zero** paused-awareness today (`load_session` doesn't even select the column); keyword-only misses most of the dataset's real handoff cases (see signal-design section above) | Still valid as a starting point, but the keyword list needs to be broadened using the dataset's actual phrasing, and `opt_out_of_messages` should probably NOT be routed through the same mechanism |
| 03-02 | 3: unsupported media -> handoff in `process_event` | — | **Confirmed live gap** — `process_event` (`processor.py:198-238`) has no branch for anything but `text`/`interactive`; other types vanish silently, `processed=TRUE`, no reply | Still fully valid and still needed |
| 03-03 | 1: `scripts/eval_agent.py` comparing tool/intent | Non-pytest script | REQ-prod-eval-gate wants pytest; a **different**, more mature but non-pipeline, non-pytest sibling (`tests/data/eval_intent.py`) already exists and duplicates much of this intent | Needs redesign, not resurrection — pytest-based, driven through `handle_message`, not a side classification prompt (see Eval-Gate Design section) |
| 03-03 | 2: hard-coded AI fallback + handoff on failure | try/except around `generate_reply`, fallback text, trigger handoff | **Fallback text: already done** (`processor.py:370-380`, `AI_FALLBACK_REPLY`). **Handoff-on-failure: not done, and currently can't fire** — `ai_service.py` swallows all its own exceptions and never lets processor's except block see a real failure in production (see AI-failure section above) | Partially done; the remaining piece (make AI failures distinguishable so a handoff can trigger) is a real open design question, not a simple task |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Retry/dead-letter for handoff-triggered alerts to the aunt | A new notification path | `processor.queue_text()` (durable outbox) + the existing `notify_permanent_failure()` loop-guard pattern | Already battle-tested (Phase 4/5), handles retries and avoids alert-storm loops |
| Handoff resolution / read APIs / dashboard UI | New endpoints, new templates | `app/services/handoff.py::resolve()`, `app/routers/operator_api.py`, `app/templates/handoffs.html` | Fully built and live (Phase 5); Phase 3 only needs to make the "active" count start being nonzero via real triggers instead of `/dev/test_handoff` |
| Audit trail | A new logging table/module | `app/services/audit.py::log_action()` + add the new action string(s) to `OPERATOR_ACTIONS` | Existing best-effort, non-blocking pattern; the trail UI already renders anything in the allowlist |
| Rate limiting / backoff for the extra Claude calls a policy-gate retry or handoff-detection tool call would add | A new limiter | `app/shared/gatekeeper.py`'s existing `execute("claude_ai", ...)` singleton | Already tuned for the worker's synchronous, bounded-wait constraints; a second limiter would double-count against `config/rate_limits.json`'s `claude_ai` budget |
| A CI pipeline just to run the eval gate | A bespoke GitHub Actions workflow invented from scratch | The existing `integration` pytest marker + `addopts` exclusion, run manually pre-release | No CI exists in this repo at all today — inventing one is a scope expansion beyond this phase's stated requirements unless explicitly asked for |

## Common Pitfalls

### Pitfall 1: Patching the wrong `query`/`execute` reference
**What goes wrong:** `app.services.handoff` does `from app.db.database import execute, query` at module load — patching `app.db.database.query` directly (rather than `app.services.handoff.query`) silently does nothing, and a test believes it's isolated from the live DB when it isn't.
**Why it happens:** Python binds the name at import time; every module in this codebase that touches the DB has its own local `query`/`execute` reference (documented explicitly in `tests/conftest.py`'s own module docstring, lines 4-9).
**How to avoid:** Always patch on the *consuming* module (`app.services.handoff`, `app.services.processor`, etc.), never on `app.db.database` itself, exactly as the existing test files already do.
**Warning signs:** A test passes locally but a real Supabase row shows up when you check — this has happened twice already in this repo's history (05-06, 05-09, per `conftest.py`'s `block_live_db` docstring).

### Pitfall 2: Assuming `generate_reply` can raise
**What goes wrong:** Building handoff-on-AI-failure logic around `processor.py`'s `except Exception` block around `generate_reply()`, not realizing `ai_service.py` already catches everything internally and never lets a real failure surface.
**Why it happens:** The code *looks* like defense-in-depth (try/except present, a test even exercises it via monkeypatch) but the exception path is dead in production given the current `ai_service.py` implementation.
**How to avoid:** Either make `ai_service.py` re-raise/signal real failures distinguishably, or accept that AI-failure handoff needs a different detection mechanism (e.g., string-matching the known fallback constants, which is fragile) — decide explicitly, don't assume the existing try/except already covers this requirement.

### Pitfall 3: Blocking the worker loop
**What goes wrong:** Adding a synchronous sleep/retry loop, an extra network call, or unbounded work inside `handle_message`/`_make_tool_executor` for policy validation or handoff detection.
**Why it happens:** `gatekeeper.py`'s docstring explains this exact failure mode already happened once before this rewrite (04-02) — a coroutine-based limiter with an unbounded sleep stalled the single-threaded worker.
**How to avoid:** Keep any new validation/detection logic to DB reads (already fast, circuit-breaker-protected via `database.py`) or pure Python — no new sleeps, no new outbound HTTP calls beyond the existing `gatekeeper.execute("claude_ai", ...)` seam if a tool-based handoff-detection call is added.

### Pitfall 4: Treating `bot_recently_active` as a lock
**What goes wrong:** Assuming the bot-vs-aunt conflict guard (`handoff.bot_recently_active`) prevents two writers from racing — it's a 5-minute heuristic on `chat_history` timestamps, explicitly documented as *not* a distributed lock (`handoff.py:24-29`).
**How to avoid:** Don't build new logic on top of it assuming stronger guarantees than it provides; it's sized for a 10-30 orders/day shop, not concurrency correctness.

## Open Questions

1. **Should AI-service failures be made distinguishable enough to trigger a handoff?**
   What we know: the fallback text already ships; the handoff-on-failure half doesn't
   currently have a reachable trigger point in production. What's unclear: whether
   changing `ai_service.py`'s exception-swallowing contract is in scope for this phase or
   a larger architectural change than intended. Recommendation: the planner should make
   this an explicit task with its own design decision documented, not bundle it silently
   into "add the fallback" (which is already done).

2. **Does `opt_out_of_messages` belong in the handoff system at all?**
   What we know: the dataset labels it as its own intent, tagged `compliance_sensitive`,
   `followup_suppression_trigger`. What's unclear: there is no consent/suppression
   mechanism anywhere in this codebase (customers table has no `opt_out`/`do_not_contact`
   column) — routing it through `handoffs` would put a compliance request in the aunt's
   manual queue rather than actually suppressing follow-ups/broadcasts. Recommendation:
   scope this phase to "hand off to a human for now" (safe, matches REQ-prod-handoff) and
   flag a real suppression mechanism as a follow-up outside Phase 3.

3. **Should a 5th `request_human_handoff` tool be added to `ai_service.py`'s `_TOOLS`
   list**, so Claude can trigger a handoff itself for cases the deterministic keyword list
   can't catch (angry tone, refund demands, privacy complaints)? What we know: the
   dataset's handoff-worthy cases are mostly sentiment/context-driven, not keyword-driven.
   What's unclear: whether adding a 5th tool changes the "one AI file, tools execute in the
   caller" contract in a way that needs its own careful design (the tool would need to call
   `handoff.trigger()`, which needs phone/session context `ai_service.py` deliberately
   doesn't have — ADR-005 in `ALYASMEEN/wiki/design-decisions.md`). Recommendation: keep
   the tool's *implementation* in `processor.py`'s tool executor (consistent with the other
   4), just add the tool *definition* to `ai_service.py`.

4. **What exact pass/fail thresholds should gate a release?** No baseline has ever been
   measured against the real `handle_message` pipeline (only the side-channel
   `eval_intent.py` has ever been run, and it evaluates a different thing). Recommendation:
   the plan should run the new eval once, unblocked, to establish a real baseline before
   picking numbers to gate on — don't invent thresholds from the stale `RESEARCH-3.md`'s
   unvalidated proposal without at least one real measurement.

5. **Is a `policy.py` module warranted, or is inline validation in `_make_tool_executor`
   enough?** Given how few actual constraints exist to enforce today (see "Don't
   Hand-Roll"/"already-grounded tools" sections), a separate `PolicyEngine` class may be
   more ceremony than the current 4-tool surface needs. Recommendation: the planner should
   size this to the real validation surface (tool-arg shape checks, the "no status-mutating
   tool exists" invariant, handoff-triggering tool-call denials) rather than the stale
   plan's more general "context includes latest order status" design, which doesn't map to
   any real tool today.

## Sources

### Primary (HIGH confidence — direct file reads, this session)
- `app/routers/whatsapp.py` — webhook receiver, full file read
- `app/services/processor.py` — full file read (bot brain, outbox, tool executors)
- `app/services/ai_service.py` — full file read (Claude integration, tool defs, fallback)
- `app/shared/gatekeeper.py` — full file read (sync rate limiter, worker constraints)
- `app/services/handoff.py` — full file read (existing resolve/active_count/bot_recently_active)
- `app/services/audit.py` — full file read (OPERATOR_ACTIONS allowlist)
- `app/routers/whatsapp_helpers.py` — full file read (session/customer/history helpers)
- `app/routers/operator_api.py` — full file read (handoffs/audit JSON API)
- `app/routers/debug.py` — full file read (`/dev/test_handoff` seed, `/dev/chat`)
- `app/routers/ui_api.py` (partial, `api_update_status`) — bot-vs-aunt conflict guard pattern
- `app/services/followup.py` — full file read (already durable via `queue_text`)
- `app/services/config.py` — full file read (env vars, `CLAUDE_MODEL`, `AUNT_PHONE`/`ADMIN_PHONE`)
- `app/db/schema.sql` (orders/sessions/order_lines sections) — status enum, paused column
- `supabase/migrations/20260614000001_durable_messaging.sql` — `handoffs`/`audit_logs`/`outbox_jobs`/`webhook_events` DDL
- `supabase/migrations/20260615000000_add_paused_to_sessions.sql` — confirms `paused` already live
- `tests/conftest.py` — full file read (FakeDB, `block_live_db`, `mock_db` patch scope, fixtures)
- `tests/unit/test_handoff_resolve.py` — full file read (existing local-patch pattern for `handoff.py`)
- `tests/unit/test_processor.py` (partial, AI-failure test) — confirms fallback reachability only via monkeypatch
- `tests/data/whatsapp_agent_dataset.json` — full dataset loaded and analyzed (75 entries, intents/tags tallied)
- `tests/data/eval_intent.py` — full file read (existing non-pytest classification evaluator)
- `tests/data/generate_noise_dataset.py` (partial) — noisy dataset generator
- `pyproject.toml` — full file read (`integration` marker, `addopts`, no CI config)
- `.planning/STATE.md` — current project state, Phase 3 staleness note, Phase 4/5 accomplishments
- `.planning/phases/03-agent-dependability-safety/03-01-PLAN.md`, `03-02-PLAN.md`, `03-03-PLAN.md` — full stale plans read
- `.planning/research/RESEARCH-3.md` — prior (also partially stale) research doc for this phase
- `ALYASMEEN/wiki/whatsapp-bot-brain.md`, `ai-service.md`, `database-tables.md`, `scheduler-jobs.md`, `design-decisions.md` — read; **confirmed stale** relative to current code (predate the outbox/processor.py refactor and Phase 4/5 entirely — no mention of processor.py, gatekeeper.py, handoff.py, audit.py, outbox_jobs, or webhook_events anywhere in the vault)
- Confirmed via `git ls-files`: `tests/data/whatsapp_agent_dataset_noisy.json` (75MB) is git-tracked

### Secondary (MEDIUM confidence)
- `.planning/ROADMAP.md` / `.planning/REQUIREMENTS.md` content as provided in the phase brief (not independently re-read this session — taken as given from the launching agent's context)

## Metadata

**Confidence breakdown:**
- Current architecture / message flow map: HIGH — every claim traced to a specific file:line via direct reads this session
- Stale-plan reconciliation: HIGH — each stale claim checked against current code, not assumed
- Policy gate / handoff trigger design recommendations: MEDIUM — grounded in existing patterns (resolve(), notify_permanent_failure(), the dataset), but no precedent in this repo for the exact new code, so these are informed proposals, not verified facts
- Eval-gate design: MEDIUM-LOW — grounded in what exists (`eval_intent.py`, the marker convention) but the threshold numbers are explicitly flagged as unvalidated; no CI exists to anchor a "how it runs in CI" answer

**Research date:** 2026-08-28
**Valid until:** Short shelf life recommended (~7-14 days) — this codebase has changed architecture twice in the past ~2 months (Phase 4 outbox rewrite, Phase 5 auth/handoff/audit build-out) and Phase 3 execution itself will immediately invalidate large parts of the "what's missing" analysis above.
