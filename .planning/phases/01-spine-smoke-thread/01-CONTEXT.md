# Phase 1: Spine Smoke-Thread - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove the production spine end-to-end: a **real** Meta Cloud API WhatsApp message is parsed
(fixing the flat-`Msg` 422 bug), routed through the existing handler, creates a **real order** in
**live Supabase**, and the **aunt's phone receives the new-order notification via the real Meta
sender**. Deliberately minimal — this proves the path *lives*; it does not harden it. Full webhook
hardening (signature verification, rate limiting, durable inbox/outbox, idempotency, web/worker
split) is **M2**; AI reliability/eval and agent safety are **M3**.

Maps requirements: **SPINE-01** (parse real Meta envelope → handler), **SPINE-02** (order in live
Supabase + aunt notified, end-to-end).
</domain>

<decisions>
## Implementation Decisions

### Proof & Verification (discussed with user)
- **D-01:** "Phase 1 done" = **full live proof, not mock.** A real WhatsApp message from a real
  phone must yield: (a) parsed inbound (no 422), (b) a real `orders`+`order_lines` row in **live
  Supabase**, visible in `/orders`, and (c) the **aunt's phone actually receiving** the new-order
  notification through the real Meta sender (`USE_MOCK_WHATSAPP=0`). A mock-only/green-tests result
  does **not** satisfy completion. (User explicitly upgraded the bar from my proposed token-free split.)
- **D-02:** The Meta token is an **in-phase prerequisite/checkpoint**, not deferred to M5. Human
  action (Khaled): obtain a working **WhatsApp Cloud API token** + **register the aunt (and Khaled)
  as test recipients** — valid even before full WABA business approval (Meta allows ≤5 test
  recipients). The planner MUST surface this as an explicit task that can BLOCK phase completion,
  and call it out loudly so it doesn't stall silently. "We do the token when we need it" = we need
  it here.
- **D-03:** The parser regression test uses a **representative Meta payload built from Meta's
  documented schema** (`entry[].changes[].value.messages[]`), committed as a fixture. No real
  captured payload required to start; may be swapped for a captured real one later. This also closes
  CONCERNS test-gap "no test covers the real Meta webhook envelope."

### Parser Strategy (Claude's discretion — decided)
- **D-04:** Add a Meta-envelope parser that normalizes the nested payload to
  `(from_number, text, wa_name)` and feeds the **existing** handler logic. **Keep the flat `Msg`
  dev/mock path working** (branch on payload shape, or accept the raw `Request` and detect shape).
  Do NOT remove the flat shape — the mock sender and all current tests depend on it. Minimal change
  to the parse seam only; order/confirm logic is untouched.

### Message-Type Scope (Claude's discretion — decided)
- **D-05:** Handle **text messages** + **interactive replies** (button/list reply → map the reply
  `id` to the command/text the handler expects, since the bot's confirm/pickup/delivery UX is
  button-driven). **Safely ignore** every other event type — especially Meta **status callbacks**
  (sent/delivered/read) which POST to the same URL — plus media/reactions: return `200`, no-op.
  Media/voice handling and human handoff are M3.

### Order-from-AI Scope (Claude's discretion — decided)
- **D-06:** The "real order" is proven through the existing **cart → confirm** path (text or
  button), producing a real order + lines row and firing the aunt notification. Phase 1 does **not**
  require exercising or validating the Claude AI/tool path — AI reliability is M3. One real
  conversation that yields one order is sufficient proof of the spine.

### Live Data Hygiene (Claude's discretion — decided)
- **D-07:** The one real smoke-test order written to live Supabase is **deleted after
  verification** (don't pollute prod). Automated parser/handler tests must not write throwaway rows
  to prod — isolate them or target the dev path.

### Response Semantics (carried / decided)
- **D-08:** `/whatsapp/*` returns `200` fast on all paths (existing global exception handler already
  does this) so Meta doesn't retry-storm. Inline processing is acceptable for the smoke-thread; the
  async worker is M2.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — Phase 1 goal + 4 success criteria
- `.planning/REQUIREMENTS.md` — SPINE-01, SPINE-02 (and the M1/M2/M3 split)
- `.planning/PROJECT.md` — Core value, constraints (HTTPS-RPC-only; keep `claude-haiku-4-5`), key decisions

### Bug being fixed
- `.planning/codebase/CONCERNS.md` — 🔴 #1 "Webhook POST cannot parse real Meta payloads" (the core of this phase) + the related test gap

### Meta webhook reference (from the harvested spike research)
- `.planning/research/ARCHITECTURE.md` — production webhook/processing architecture (reference, verify before acting)
- `.planning/research/PITFALLS.md` — common Meta Cloud API / webhook mistakes

### Code to modify / reuse
- `app/routers/whatsapp.py:154-172` — `webhook_get`, `Msg` model, `webhook_post` (the parse seam to change)
- `app/services/whatsapp_meta.py` — `verify_get`, `send_text`, `send_buttons` (real sender path for the live proof)
- `app/services/whatsapp_dev.py` — mock sender (must keep working)
- `app/routers/whatsapp_helpers.py` — session/customer/order helpers (unchanged)
- `app/db/database.py` — `execute` / `execute_returning` (order insert; `%s` only)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The whole `webhook_post` hard-command dispatcher + `confirm` → order insert → aunt-notify flow
  already exists (`whatsapp.py`). We change only how the inbound message is *parsed*, not the order
  logic — so most of the spine is already built.
- Sender swap via `Config.USE_MOCK_WHATSAPP` (`whatsapp_dev` vs `whatsapp_meta`) — flip to real for
  the live proof.
- `verify_get` already handles the GET webhook handshake (Meta verification).

### Established Patterns
- Flat `Msg` Pydantic model is the current POST contract; mock + tests depend on it → preserve it.
- All `/whatsapp/*` responses are forced to `200` via the global exception handler (anti-retry-storm).
- SQL via the single DB adapter with `%s` placeholders; HTTPS-RPC-only (no psycopg2 / DATABASE_URL).

### Integration Points
- New parser sits at the `POST /webhook` boundary, flattening the Meta envelope → existing handler.
- Real send path = `whatsapp_meta` → needs `WA_META_TOKEN`, `WA_META_PHONE_ID` (the D-02 token task).
</code_context>

<specifics>
## Specific Ideas

- User insists on a **real** end-to-end proof — the aunt's phone must actually buzz from a real
  message before this phase counts as done. Trust nothing until seen working live (no mock pass).
</specifics>

<deferred>
## Deferred Ideas

- Webhook signature verification (`WA_META_APP_SECRET`), rate limiting, durable inbox/outbox +
  web/worker split, `wamid` idempotency → **M2**
- AI reliability/fallbacks, eval harness, agent policy gate + human handoff, media/voice handling →
  **M3**
- Full Meta WABA business approval (messaging arbitrary customers beyond the ≤5 test recipients) →
  **M5**

None of the above is in Phase 1 scope — discussion stayed within the smoke-thread boundary.
</deferred>

---

*Phase: 1-Spine Smoke-Thread*
*Context gathered: 2026-06-14*
