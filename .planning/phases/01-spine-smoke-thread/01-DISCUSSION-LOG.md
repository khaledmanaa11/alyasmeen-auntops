# Phase 1: Spine Smoke-Thread - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-14
**Phase:** 1-Spine Smoke-Thread
**Areas discussed:** Proof without token (selected); Parser strategy / Message-type scope / Order-from-AI scope (delegated to Claude)

---

## Gray-area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Parser strategy | Meta-envelope parse alongside flat dev `Msg` vs replace | (delegated to Claude) |
| Message-type scope | text only vs text + button replies; ignore status callbacks | (delegated to Claude) |
| Proof without token | token-free now + live checkpoint vs full live now | ✓ |
| Order-from-AI scope | full AI/cart/confirm vs minimal one-message→order | (delegated to Claude) |

**User's choice:** Discuss only "Proof without token"; let Claude decide and record the other three.

---

## Proof without token

**Question 1 — define "Phase 1 done":**

| Option | Description | Selected |
|--------|-------------|----------|
| Token-free now + live checkpoint | Prove parse + order + MOCK aunt-notify now; real send-to-aunt is a later checkpoint | |
| Full live now | Sort the Meta token first; prove the real send-to-aunt before Phase 1 is done | ✓ |

**User's choice:** Full live now.
**Notes:** User upgraded the bar above Claude's recommendation — wants the aunt's phone to actually buzz from a real message before counting Phase 1 done. Reconciled with "do the token when we need it" = the token is needed in Phase 1. Meta's ≤5 test-recipient allowance makes this achievable pre-WABA-approval.

**Question 2 — Meta payload fixture source:**

| Option | Description | Selected |
|--------|-------------|----------|
| Build from Meta's documented schema | Construct a representative nested payload now; no Meta account needed | ✓ |
| Wait for a captured real payload | Capture a real payload first, then build the test | |

**User's choice:** Build from Meta's documented schema.
**Notes:** Unblocks the parser test today; can swap in a captured payload later.

---

## Claude's Discretion

- **Parser strategy** → add a Meta-envelope normalizer that flattens to `(from_number, text, wa_name)` and keeps the flat `Msg` dev/mock path + tests working (D-04).
- **Message-type scope** → handle text + interactive button/list replies; safely ignore status callbacks, media, reactions (D-05).
- **Order-from-AI scope** → prove via the existing cart→confirm path; AI/tool path not required in Phase 1 (D-06).
- **Live data hygiene** → delete the one smoke-test order after verifying; don't pollute prod with automated test rows (D-07).
- **Response semantics** → keep `/whatsapp/*` returning 200 fast; inline processing OK (async worker is M2) (D-08).

## Deferred Ideas

- Webhook signature verify, rate limiting, inbox/outbox + worker split, `wamid` idempotency → M2
- AI reliability/eval, agent policy gate + handoff, media/voice handling → M3
- Full WABA business approval (arbitrary customers beyond ≤5 test recipients) → M5
