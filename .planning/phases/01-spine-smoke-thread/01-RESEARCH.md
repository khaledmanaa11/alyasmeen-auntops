# Phase 1: Spine Smoke-Thread - Research

**Researched:** 2026-06-15
**Domain:** WhatsApp Meta Cloud API inbound webhook parsing (brownfield seam fix)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** "Phase 1 done" = **full live proof, not mock.** A real WhatsApp message from a real
  phone must yield: (a) parsed inbound (no 422), (b) a real `orders`+`order_lines` row in **live
  Supabase**, visible in `/orders`, and (c) the **aunt's phone actually receiving** the new-order
  notification through the real Meta sender (`USE_MOCK_WHATSAPP=0`). A mock-only/green-tests result
  does **not** satisfy completion.
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

### Claude's Discretion
- **D-04:** Add a Meta-envelope parser that normalizes the nested payload to
  `(from_number, text, wa_name)` and feeds the **existing** handler logic. **Keep the flat `Msg`
  dev/mock path working** (branch on payload shape, or accept the raw `Request` and detect shape).
  Do NOT remove the flat shape — the mock sender and all current tests depend on it. Minimal change
  to the parse seam only; order/confirm logic is untouched.
- **D-05:** Handle **text messages** + **interactive replies** (button/list reply → map the reply
  `id` to the command/text the handler expects). **Safely ignore** every other event type —
  especially Meta **status callbacks** (sent/delivered/read) which POST to the same URL — plus
  media/reactions: return `200`, no-op.
- **D-06:** The "real order" is proven through the existing **cart → confirm** path (text or
  button), producing a real order + lines row and firing the aunt notification. Phase 1 does **not**
  require exercising or validating the Claude AI/tool path.
- **D-07:** The one real smoke-test order written to live Supabase is **deleted after
  verification**. Automated parser/handler tests must not write throwaway rows to prod — isolate
  them or target the dev path.
- **D-08:** `/whatsapp/*` returns `200` fast on all paths (existing global exception handler already
  does this) so Meta doesn't retry-storm. Inline processing is acceptable for the smoke-thread; the
  async worker is M2.

### Deferred Ideas (OUT OF SCOPE)
- Webhook signature verification (`WA_META_APP_SECRET`), rate limiting, durable inbox/outbox +
  web/worker split, `wamid` idempotency → **M2**
- AI reliability/fallbacks, eval harness, agent policy gate + human handoff, media/voice handling →
  **M3**
- Full Meta WABA business approval (messaging arbitrary customers beyond the ≤5 test recipients) →
  **M5**
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SPINE-01 | A real Meta Cloud API webhook payload (nested envelope) is parsed into `(from_number, text, wa_name)` and reaches the existing message handler (minimal parser only; full webhook hardening is M2) | Verified envelope schema (Standard Stack + Architecture Patterns), shape-detection seam design (Pattern 1), interactive-reply→command map (Pattern 2). Regression fixture (D-03) covered by Validation Architecture. |
| SPINE-02 | An order placed from a real WhatsApp message is written to live Supabase and the aunt receives the new-order notification — proven end-to-end | Existing `confirm`→order→aunt-notify flow at `whatsapp.py:262-323` is reused unchanged; live-proof checkpoint + token prerequisite (D-02) covered in Environment Availability and Validation Architecture (manual live gate). |
</phase_requirements>

## Summary

This is a **brownfield seam fix**, not a build. The entire ordering spine — hard-command dispatcher,
cart, `confirm` → `orders`+`order_lines` insert, and the new-order notification to the aunt — already
exists and is exercised end-to-end in mock mode (`app/routers/whatsapp.py:262-323`). The single broken
seam is the inbound parse: `webhook_post(msg: Msg)` (`whatsapp.py:171-172`) declares a **flat** Pydantic
body `Msg{from_number, text, wa_name}`. FastAPI validates the request body against `Msg` **before any of
your code runs**, so a real Meta Cloud API envelope (`{object, entry[].changes[].value.messages[]}`)
fails validation and returns **HTTP 422**. The fix is to stop binding the body to `Msg`, accept the raw
`Request`, detect payload shape, and normalize the nested Meta envelope to the same
`(from_number, text, wa_name)` tuple the existing handler already consumes.

The Meta envelope structure is now verified at HIGH confidence against Meta's own official Node.js SDK
type definitions (`WhatsApp/WhatsApp-Nodejs-SDK`, `src/types/webhooks.ts`) — it matches the harvested
`ARCHITECTURE.md`/`CONCERNS.md` description exactly. A single POST URL receives **three** payload kinds
that must be distinguished: inbound **messages** (`value.messages[]`), **status callbacks**
(`value.statuses[]` — sent/delivered/read, which fire constantly and must be a 200 no-op per D-05), and
the flat dev `Msg` shape (no `object`/`entry`). The bot's interactive UX is button-driven, so the parser
must also map an inbound `interactive.button_reply.id` (e.g. `confirm`, `pickup`, `delivery`, `clear`,
`cart`) back to the command text the existing dispatcher expects — these IDs are already emitted by
`send_buttons` in this codebase, so the mapping is an identity pass-through (`id` → `text`).

The hard part of this phase is **not** the code (a ~40-line parser). It is **D-02**: Khaled must obtain a
working Cloud API token and register the aunt + himself as test recipients in Meta. This is a human,
external, blocking prerequisite for the D-01 live proof. The temporary token expires in 24 hours, so the
live-proof test must be run shortly after the token is minted, or a 60-day/permanent System User token
must be generated first.

**Primary recommendation:** Change the POST seam to `async def webhook_post(request: Request)`; read
`await request.json()`; branch on `body.get("object") == "whatsapp_business_account"`; iterate
`entry[].changes[].value` and process only `field == "messages"` changes that contain `messages[]`;
extract `from`, the text/interactive payload, and `contacts[0].profile.name`; map interactive reply `id`
→ command text; then call the existing handler logic. Status callbacks and unsupported types return
`200` no-op. Keep the flat `Msg` branch intact for dev/mock and every existing test.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Inbound webhook parse (Meta envelope → tuple) | API / Backend (`whatsapp.py` POST route) | — | The webhook is a server-side ingress; parsing belongs at the route boundary, not in any sender/helper |
| Shape detection (flat vs nested vs status) | API / Backend (POST route) | — | Must happen before handler dispatch; it is request-handling concern |
| Interactive reply `id` → command text mapping | API / Backend (parser) | — | Translation of provider-specific payload into the handler's existing command vocabulary |
| Order create + lines write | Database / Storage (`execute_returning`/`execute` via `database.py`) | API (handler issues SQL) | Already implemented; single DB adapter owns persistence; phase reuses unchanged |
| Outbound send (customer reply + aunt notify) | API / Backend (`whatsapp_meta.send_text`) | External (Meta Send API) | Already implemented; flip `USE_MOCK_WHATSAPP=0` for live proof |
| Token + test-recipient provisioning | External (Meta Business portal — human) | — | D-02 human prerequisite; no code owns this; gates the live send |

## Standard Stack

This phase introduces **no new libraries**. It is a code change inside an existing, fully-wired stack.
The "stack" relevant to the phase is the already-installed transport and framework layer.

### Core (already present — verified in `requirements.txt` / imports)
| Library | Version (verify at install) | Purpose | Why Standard |
|---------|------------------------------|---------|--------------|
| `fastapi` | installed | Webhook route + `Request`/`Response` handling | Already the app framework; `Request` gives raw-body access for shape detection `[VERIFIED: codebase app/main.py, whatsapp.py]` |
| `pydantic` | installed (FastAPI dep) | Existing flat `Msg` model (dev/mock path — keep) | Already the POST contract for tests/mock `[VERIFIED: codebase whatsapp.py:165-168]` |
| `requests` | installed | Outbound Meta Cloud API `POST /messages` | Already used by `whatsapp_meta.send_text`/`send_buttons` `[VERIFIED: codebase app/services/whatsapp_meta.py:5,34]` |

### Supporting (Meta Cloud API — external service, not a package)
| Endpoint / Surface | Version | Purpose | When to Use |
|--------------------|---------|---------|-------------|
| Meta Graph API `/{phone_id}/messages` | `v19.0` (hardcoded in `whatsapp_meta.py:26`) | Outbound send for the live proof | On `confirm` (customer reply + aunt notify). `v19.0` still functional but Meta version lifecycle should be reviewed in M2 (not this phase). `[CITED: graph.facebook.com versioning]` `[VERIFIED: codebase whatsapp_meta.py:26]` |
| Webhook subscription (Meta App → WhatsApp → Configuration) | — | Routes inbound to `POST /whatsapp/webhook` | Human setup, part of D-02 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `Request` + manual shape detection | Two FastAPI routes / `Union[FlatMsg, MetaEnvelope]` Pydantic model | A `Union` body model is more "typed" but (a) Meta's envelope has many optional message types that are painful to model fully, (b) status callbacks have no `messages[]` and would need their own model, (c) `discriminated unions` add complexity for a minimal seam. Raw `Request` + `dict.get()` traversal is the smallest change that satisfies D-04/D-08 and is the approach the harvested `ARCHITECTURE.md` Pattern 1 also uses (`await request.body()` / `parse_meta_envelope`). |
| Single POST route handling all shapes | Separate `/webhook/meta` route | Meta requires one configured callback URL; the dev/mock path already posts to `/whatsapp/webhook`. One route, branch inside. |

**Installation:** None. No `pip install`. (Package Legitimacy Audit below confirms zero new packages.)

**Version verification:** No new package versions to verify. The Meta Graph API version (`v19.0`) is a
runtime endpoint string, not a package — its lifecycle review is explicitly deferred to M2 per the
scope fences. `[CITED: .planning/research/ARCHITECTURE.md "Pin the Meta Graph API version ... must be validated before M2"]`

## Package Legitimacy Audit

> This phase installs **no external packages**. It modifies existing code (`app/routers/whatsapp.py`)
> and adds a test fixture + test. The slopcheck gate is therefore **N/A** — there are no install
> candidates to verify.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| (none) | — | — | — | — | — | No packages added this phase |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

All transport libraries (`fastapi`, `pydantic`, `requests`) are already present in the repo and in use;
this phase adds nothing to `requirements.txt`. If the planner discovers a need for a new dependency
(it should not), gate it behind a `checkpoint:human-verify` task.

## Architecture Patterns

### System Architecture Diagram

```text
  Customer phone (real)                          Aunt phone (real)
        │                                              ▲
        │ sends WhatsApp msg                           │ new-order notification
        ▼                                              │ (USE_MOCK_WHATSAPP=0)
  ┌──────────────────────────────────────────────┐    │
  │ Meta Cloud API                                │    │
  │  - delivers inbound as nested envelope        │    │
  │  - ALSO POSTs status callbacks (sent/         │    │
  │    delivered/read) to the SAME URL            │    │
  └───────────────┬──────────────────────────────┘    │
                  │ HTTPS POST                          │
                  ▼  /whatsapp/webhook                  │
  ┌──────────────────────────────────────────────┐    │
  │ webhook_post(request: Request)   [THE SEAM]   │    │
  │                                               │    │
  │  raw = await request.json()                   │    │
  │  ┌─ shape detect ────────────────────────┐    │    │
  │  │ object=="whatsapp_business_account"?   │    │    │
  │  │   ├─ value.messages[] present?         │    │    │
  │  │   │    type=="text" → text.body        │    │    │
  │  │   │    type=="interactive" → reply.id  │    │    │
  │  │   │    from, contacts[0].profile.name  │    │    │
  │  │   │    → (from_number, text, wa_name)  │    │    │
  │  │   ├─ value.statuses[] present? → 200 no-op   │    │
  │  │   └─ other type → 200 no-op            │    │    │
  │  │ else (flat dev Msg shape)              │    │    │
  │  │   → from_number, text, wa_name         │    │    │
  │  └────────────────────────────────────────┘   │    │
  │                  │ normalized tuple             │   │
  │                  ▼                              │    │
  │  EXISTING handler logic (UNCHANGED)            │    │
  │   aliases → hard cmds → number/qty → AI        │    │
  │   on "confirm": ─────────────────────────────────┐ │
  └──────────────────────────────────────────────┘  │ │
                  │ INSERT orders + order_lines        │ │
                  ▼  (execute_returning / execute)     │ │
  ┌──────────────────────────────────────────────┐   │ │
  │ database.py  (HTTPS-RPC, %s placeholders)     │   │ │
  │   → live Supabase  orders / order_lines       │   │ │
  │   → visible in /orders dashboard              │   │ │
  └──────────────────────────────────────────────┘   │ │
                                                       │ │
   send_text(customer, "تم إنشاء الطلب…")  ◄───────────┘ │
   send_text(Config.AUNT_PHONE, "🛍️ طلب جديد…")  ◄───────┘
   (whatsapp_meta.send_text → Meta Send API, real)
```

Trace the primary use case (SPINE-01 + SPINE-02): real message enters via Meta → parsed at the seam →
normalized tuple → existing handler → `confirm` writes order to live Supabase → aunt notified via real
Meta sender. The **only** new code is the shape-detect/normalize block; everything below "EXISTING
handler logic" is reused verbatim.

### Recommended Project Structure
No structural change. The edit is localized:
```
app/
├── routers/
│   └── whatsapp.py          # EDIT: webhook_post seam only (lines 171-172 → raw Request + parser)
│                            # ADD:  _parse_meta_envelope() helper (same file or whatsapp_helpers.py)
tests/
├── data/
│   └── meta_webhook_*.json  # ADD:  documented-schema fixtures (D-03): text, button_reply, list_reply, status
└── unit/
    └── test_whatsapp_meta_envelope.py   # ADD: parser regression tests (D-03)
```

Keep the parser helper **pure** (input: `dict` body → output: list of `(from_number, text, wa_name)`
tuples or `None`/empty for no-op). A pure function is trivially unit-testable against fixtures without
a `TestClient`, and keeps the route thin. The existing dispatcher body is large (`whatsapp.py:172-486`);
do NOT inline more logic into it — wrap it or extract the normalized-tuple entry so both shapes call it.

### Pattern 1: Shape-Detection at the POST Seam (the core change)
**What:** Stop binding the request body to the flat `Msg` model. Accept raw `Request`, parse JSON, and
branch on the presence of the Meta envelope discriminator.
**When to use:** This is THE change for SPINE-01.
**Why it works:** FastAPI runs Pydantic body validation *before* the handler. With `msg: Msg`, a nested
payload 422s before any branch can run. Switching to `request: Request` defers all parsing to your code.
The dev/mock shape (`{"from_number","text","wa_name"}`) has no top-level `object` key; the Meta shape
always has `object: "whatsapp_business_account"`. That single key is a reliable discriminator.
**Example:**
```python
# Source: pattern derived from Meta SDK envelope (WhatsApp/WhatsApp-Nodejs-SDK src/types/webhooks.ts)
#         + harvested ARCHITECTURE.md Pattern 1; adapted to this codebase's existing handler.
from fastapi import Request

@router.post("/webhook")
async def webhook_post(request: Request):
    body = await request.json()

    # --- Meta Cloud API envelope ---
    if body.get("object") == "whatsapp_business_account":
        for parsed in _parse_meta_envelope(body):   # list of (from, text, wa_name)
            _handle_message(*parsed)                 # existing dispatcher logic, extracted
        return {"ok": True}                          # 200 even when nothing actionable (status cb etc.)

    # --- Flat dev/mock shape (KEEP — tests + mock depend on it) ---
    from_number = body.get("from_number", "")
    text = body.get("text", "")
    wa_name = body.get("wa_name")
    return _handle_message(from_number, text, wa_name)
```
**Note on D-08 / async:** the current handler body is sync (`def webhook_post`). It calls blocking
`requests.post` (Meta) and blocking Supabase RPC. If you make the route `async def`, those blocking calls
run on the event loop and will stall it. Two safe options: (a) keep the route `def` and read the body
synchronously — FastAPI exposes the body via `Request` but `await` requires async; the simplest sync
path is to keep `def webhook_post(request: Request)` and use Starlette's sync access is NOT available, so
(b) make it `async def`, do `await request.json()`, then dispatch the existing **sync** handler. Because
volume is tiny and the async worker is M2 (D-08 permits inline processing), running the sync handler
inside the async route is acceptable for the smoke-thread — but be aware it briefly blocks the loop.
`[ASSUMED]` — the planner should confirm whether to wrap the sync handler in `run_in_threadpool` or
accept the brief inline block; either satisfies D-08's "inline processing acceptable" but the threadpool
wrap is the cleaner minimal choice. Flag A1.

### Pattern 2: Interactive Reply → Command Identity Map (D-05)
**What:** Map an inbound `interactive.button_reply.id` / `list_reply.id` to the text the existing
dispatcher already branches on.
**When to use:** Button/list taps in the cart/fulfillment UX.
**Why it's nearly free here:** This codebase's `send_buttons` sets reply IDs to the **exact command
strings** the dispatcher checks. Verified emitted IDs:

| Reply `id` emitted by `send_buttons` | Where | Handler branch that consumes it |
|--------------------------------------|-------|----------------------------------|
| `confirm` | `whatsapp.py:224,258,338` | `if low == "confirm"` (`:262`) |
| `clear` | `whatsapp.py:225,229` | `if low == "clear"` (`:232`) |
| `pickup` | `whatsapp.py:227,382,408` | `if low in ("pickup","delivery")` (`:239`) |
| `delivery` | `whatsapp.py:228,339,383,409` | same (`:239`) |
| `cart` | `whatsapp.py:384,410` | `if low == "cart"` (`:206`) |

So the parser maps `interactive.*.id` → `text = id`, and the existing handler does the rest. **No new
command vocabulary is needed.** The numbered product menu uses free **text** numbers ("1","2"), not
interactive list rows (the menu is sent via `send_text`, `whatsapp.py:359`), so list_reply mapping is
defensive-only for Phase 1 — still parse it (map `list_reply.id` → text) so a future list menu works,
but it is not on the critical proof path.
**Example:**
```python
# Source: codebase whatsapp.py send_buttons IDs (verified) + Meta SDK interactive shape
def _interactive_to_text(interactive: dict) -> str:
    itype = interactive.get("type")              # "button_reply" | "list_reply"
    reply = interactive.get(itype, {}) if itype else {}
    return (reply.get("id") or "").strip()       # id IS the command (confirm/pickup/…)
```

### Pattern 3: Status-Callback No-Op (D-05, anti-retry-storm)
**What:** Meta POSTs `value.statuses[]` (sent/delivered/read) to the same URL, constantly, with NO
`messages[]`. These must be a fast `200` no-op.
**Why critical:** If the parser assumes `value.messages[0]` exists, every status callback raises
`IndexError`/`KeyError`. The global handler currently swallows that into a 200 (`main.py:83-87`), so it
wouldn't retry-storm — but it WOULD spam error logs and mask real failures. Detect `messages` presence
explicitly; if absent (or `field != "messages"`, or it's a status), return 200 without touching the
handler.

### Anti-Patterns to Avoid
- **Re-introducing a strict Pydantic body model that 422s on Meta shapes** — this is the exact bug.
  The whole point of D-04 is to accept the raw request and branch.
- **Assuming `value.messages[0]` always exists** — status callbacks and other change types have no
  `messages`. Guard every index.
- **Pulling M2 hardening into the parser** — do NOT add `X-Hub-Signature-256` verification, `wamid`
  idempotency, or an inbox table. `verify_get` already has a (dormant) signature branch; leave it. The
  scope fence is explicit.
- **Changing `confirm`/order/notify logic** — D-04/D-06 forbid it. The order path is proven; touching it
  risks the live proof for no benefit.
- **Removing the flat `Msg` model** — every test in `tests/` and the dev workflow depend on it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Outbound WhatsApp send | A new sender | Existing `whatsapp_meta.send_text`/`send_buttons` | Already implemented + `USE_MOCK_WHATSAPP` swap `[VERIFIED: codebase whatsapp_meta.py]` |
| Order persistence | New insert logic | Existing `confirm` branch (`whatsapp.py:262-323`) | Proven order+lines+notify flow |
| Webhook GET verification | New handshake | Existing `verify_get` (`whatsapp_meta.py:158`) | Already handles `hub.*` challenge `[VERIFIED]` |
| Multi-event batch handling | Custom queue | Loop over `entry[]`/`changes[]` inline | Meta batches events; loop and process each (D-08 inline OK) |
| Signature verification (HMAC) | Anything | **Nothing — it's M2** | Out of scope; `WA_META_APP_SECRET` stays unused this phase |

**Key insight:** The spine is built. The only honest "new" work is ~40 lines of dict traversal +
fixtures + tests. Resist the gravity of the harvested research (which describes the full M2 inbox/outbox
architecture) — almost all of it is explicitly out of scope here.

## Runtime State Inventory

> This phase is a **seam fix**, not a rename/refactor/migration — but it does flip one runtime config
> (`USE_MOCK_WHATSAPP`) and creates one real prod row that must be cleaned up (D-07). Inventory below.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | One real `orders` row + its `order_lines` row(s) created by the live smoke-test (D-01) in **live Supabase** | **Data deletion** after verification (D-07): delete the smoke order + its lines. Also the test customer's `sessions` row is cleared by the existing `confirm` flow (`clear_session`, `whatsapp.py:299`); a `customers` row + `chat_history` may persist — decide whether to delete (recommend: delete the test customer's order/lines/session; leaving one `customers` row is low-harm but note it). |
| Live service config | Meta App webhook subscription must point at the deployed `POST /whatsapp/webhook` URL; the WhatsApp number must be registered to receive | Human (D-02): configure callback URL + verify token in Meta App → WhatsApp → Configuration. This config lives in Meta's portal, NOT in git. |
| OS-registered state | None — no OS scheduler/service registers the renamed/changed string | None — verified: the only scheduler is APScheduler in-process (`main.py:50-62`), unaffected by this phase. |
| Secrets/env vars | `WA_META_TOKEN`, `WA_META_PHONE_ID`, `WA_META_VERIFY_TOKEN` must be set in the runtime env; `USE_MOCK_WHATSAPP` must be flipped to `0` for the live proof | Set in Railway/runtime env (D-02). These are read at import time in `whatsapp.py:29-32` — **the mock-vs-real sender is bound at module import**, so changing `USE_MOCK_WHATSAPP` requires a process restart (see Pitfall 4). Verified `[whatsapp.py:29-32, config.py:20]`. |
| Build artifacts | None — pure source edit; no compiled artifact, no package rebuild | None. |

**The canonical question — after every file is updated, what runtime systems still hold old state?**
The one real prod `orders`/`order_lines` row from the live test (D-07 cleanup) and the Meta-portal
webhook subscription (human config, not git). Both are explicitly accounted for above.

## Common Pitfalls

### Pitfall 1: The 422 happens before your code — you cannot "catch" it in the handler
**What goes wrong:** Engineers add envelope-parsing logic *inside* `webhook_post` but leave the
`msg: Msg` signature. Meta payloads still 422 because FastAPI validates the body against `Msg` first.
**Why it happens:** Misunderstanding FastAPI's request lifecycle — body validation precedes the function.
**How to avoid:** The signature MUST change from `def webhook_post(msg: Msg)` to
`async def webhook_post(request: Request)`. That is the load-bearing edit. `[VERIFIED: codebase whatsapp.py:171-172]`
**Warning signs:** Real payload returns 422 even after you "added a parser."

### Pitfall 2: Status callbacks crash the parser (KeyError on `messages[0]`)
**What goes wrong:** `value.statuses[]` events have no `messages` key. Naive `value["messages"][0]`
raises. Meta sends these on *every* message you send (sent → delivered → read), so they're high-volume.
**Why it happens:** Status callbacks share the POST URL (D-05 calls this out explicitly).
**How to avoid:** Check `"messages" in value` (and `change.get("field") == "messages"`) before indexing;
if absent, return 200 no-op. Verified shape: `StatusesObject{status, id, recipient_id, timestamp}` lives
in `value.statuses[]`, never alongside a `messages[]` you care about. `[VERIFIED: Meta SDK webhooks.ts ValueObject]`
**Warning signs:** Error logs fill with KeyError/IndexError while HTTP stays 200 (the global handler
masks it — `main.py:83`).

### Pitfall 3: Temporary token expires in 24h mid-test
**What goes wrong:** Khaled mints the test token, the live proof slips a day, the send fails with an
auth error, and the phase appears "broken" when it's just an expired token.
**Why it happens:** Meta's setup-page temporary token expires every 24 hours. `[CITED: developers.facebook.com/blog/post/2022/12/05/auth-tokens]`
**How to avoid:** Either (a) run the live proof within 24h of minting the temp token, or (b) generate a
**System User** token (whatsapp_business_messaging + whatsapp_business_management, ~60-day or
non-expiring) before the proof. The planner should prefer (b) so the proof window isn't a stopwatch.
**Warning signs:** Outbound send returns HTTP 401/190 (`OAuthException`). `[ASSUMED]` exact error code —
flag A2.

### Pitfall 4: Sender is bound at import — flipping `USE_MOCK_WHATSAPP` needs a restart
**What goes wrong:** Operator sets `USE_MOCK_WHATSAPP=0` in a running process and expects real sends; the
import-time branch (`whatsapp.py:29-32`) already bound `send_text` to the mock at startup.
**Why it happens:** `if Config.USE_MOCK_WHATSAPP: from whatsapp_dev import …` runs once at module load.
`[VERIFIED: codebase whatsapp.py:29-32]`
**How to avoid:** Set the env var **before** process start; restart the process for the live proof.
(Note: `whatsapp_meta.send_text` *also* re-checks `Config.USE_MOCK_WHATSAPP` at call time and delegates
to dev if true — `whatsapp_meta.py:22-24` — but the *import binding* in `whatsapp.py` decides which
module's `send_text` is even called. Both must agree → set env, restart.)
**Warning signs:** Messages print to console (`[DEV]`) instead of arriving on the phone.

### Pitfall 5: Recipient not in the ≤5 test list → silent-ish failure
**What goes wrong:** Pre-WABA-approval, Meta only delivers to phone numbers explicitly added as test
recipients. If the aunt's number isn't registered, the new-order notification never arrives (failing
D-01's "aunt's phone actually buzzes") even though the code ran.
**Why it happens:** Cloud API restricts unverified apps to ≤5 manually-added recipients. `[CITED: developers.facebook.com get-started; verified via multiple sources]`
**How to avoid:** D-02 task must register BOTH the aunt's number AND Khaled's test number in
Meta App → WhatsApp → API Setup → recipient list, before the proof. Verify the list shows both.
**Warning signs:** Send returns 200/`messages[].id` but no message arrives (recipient error
`#131030`/`131026` in delivery status). `[ASSUMED]` exact code — flag A3.

### Pitfall 6: Webhook GET verify token mismatch blocks subscription
**What goes wrong:** Meta's webhook subscription GET handshake fails because `WA_META_VERIFY_TOKEN` in
the env doesn't match what's typed into the Meta App config form.
**Why it happens:** `verify_get` checks `token == Config.WA_META_VERIFY_TOKEN` (`whatsapp_meta.py:177`).
**How to avoid:** Set `WA_META_VERIFY_TOKEN` to a known value; type the exact same string into Meta's
"Verify token" field when subscribing. The GET path already works (`webhook_get`, `whatsapp.py:154-162`)
and returns `PlainTextResponse(challenge)`. `[VERIFIED: codebase]`
**Warning signs:** Meta UI says "verification failed"; the subscription won't save.

## Code Examples

### Verified Meta inbound envelope — TEXT message (build the D-03 fixture from this)
```jsonc
// Source: Meta official Node.js SDK type defs (WhatsApp/WhatsApp-Nodejs-SDK src/types/webhooks.ts)
//         WebhookObject → Entry_Object → ChangesObject → ValueObject → MessagesObject
// [VERIFIED: github.com/WhatsApp/WhatsApp-Nodejs-SDK src/types/webhooks.ts]
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "WABA_ID",
    "changes": [{
      "field": "messages",
      "value": {
        "messaging_product": "whatsapp",
        "metadata": { "display_phone_number": "15550001111", "phone_number_id": "PHONE_ID" },
        "contacts": [{ "profile": { "name": "فاطمة" }, "wa_id": "972599123456" }],
        "messages": [{
          "from": "972599123456",
          "id": "wamid.HBgM...",
          "timestamp": "1718450000",
          "type": "text",
          "text": { "body": "menu" }
        }]
      }
    }]
  }]
}
// from_number = entry[0].changes[0].value.messages[0].from         → "972599123456"
// text        = entry[0].changes[0].value.messages[0].text.body    → "menu"
// wa_name     = entry[0].changes[0].value.contacts[0].profile.name → "فاطمة"
```

### Verified Meta inbound envelope — INTERACTIVE button_reply
```jsonc
// [VERIFIED: Meta SDK ButtonReplyObject + WebSearch official JSON example]
// NOTE: on the wire, interactive has BOTH a discriminator `type` AND a sibling key named after it.
{
  "object": "whatsapp_business_account",
  "entry": [{ "changes": [{ "field": "messages", "value": {
    "messaging_product": "whatsapp",
    "contacts": [{ "profile": { "name": "فاطمة" }, "wa_id": "972599123456" }],
    "messages": [{
      "from": "972599123456",
      "id": "wamid.HBgM...",
      "timestamp": "1718450050",
      "type": "interactive",
      "interactive": {
        "type": "button_reply",
        "button_reply": { "id": "confirm", "title": "✅ تأكيد الطلب" }
      }
    }]
  }}]}]
}
// command text = interactive.button_reply.id → "confirm"  (maps directly to handler branch)
```

### Verified Meta inbound envelope — INTERACTIVE list_reply (defensive parse only this phase)
```jsonc
// [VERIFIED: Meta SDK ListReplyObject { id, title, description }]
"interactive": {
  "type": "list_reply",
  "list_reply": { "id": "prod_1", "title": "كريم اليدين", "description": "25₪" }
}
// command text = interactive.list_reply.id → "prod_1"
```

### Verified Meta envelope — STATUS callback (must be 200 no-op, D-05)
```jsonc
// [VERIFIED: Meta SDK StatusesObject; lives in value.statuses[], NO messages[]]
{
  "object": "whatsapp_business_account",
  "entry": [{ "changes": [{ "field": "messages", "value": {
    "messaging_product": "whatsapp",
    "metadata": { "display_phone_number": "15550001111", "phone_number_id": "PHONE_ID" },
    "statuses": [{
      "id": "wamid.HBgM...",
      "status": "delivered",            // or "sent" | "read"
      "timestamp": "1718450100",
      "recipient_id": "972599123456"
    }]
  }}]}]
}
// No `messages` key → parser returns [] → route returns 200, handler never called.
```

### Reference parser skeleton (pure, fixture-testable)
```python
# Source: derived from verified Meta envelope; satisfies D-04 (normalize) + D-05 (ignore non-message)
def _parse_meta_envelope(body: dict) -> list[tuple[str, str, str | None]]:
    """Flatten a Meta webhook into [(from_number, text, wa_name), ...].
    Returns [] for status callbacks and unsupported types (caller returns 200 no-op)."""
    out: list[tuple[str, str, str | None]] = []
    for entry in body.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            messages = value.get("messages")
            if not messages:                      # status callback / no inbound msg → ignore
                continue
            contacts = value.get("contacts") or []
            wa_name = (contacts[0].get("profile", {}).get("name")
                       if contacts else None)
            for m in messages:
                frm = m.get("from", "")
                mtype = m.get("type")
                if mtype == "text":
                    text = (m.get("text") or {}).get("body", "")
                elif mtype == "interactive":
                    inter = m.get("interactive") or {}
                    sub = inter.get("type")        # button_reply | list_reply
                    text = ((inter.get(sub) or {}).get("id", "") if sub else "")
                else:
                    continue                        # media/reaction/etc → ignore (D-05)
                if frm and text:
                    out.append((frm, text, wa_name))
    return out
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat `Msg{from_number,text,wa_name}` POST body | Nested Meta envelope `entry[].changes[].value.messages[]` | Meta Cloud API has used this envelope since launch (2022) | The flat shape was a dev/mock invention; real Meta never sent it → the 422 bug |
| `@app.on_event("startup")` (in `main.py`) | FastAPI `lifespan` context manager | FastAPI 0.93+ deprecated on_event | Noted in CONCERNS as debt; **out of scope this phase** (M2) — do not change |

**Deprecated/outdated:**
- Nothing in the parse seam is deprecated. Graph API `v19.0` still works but its lifecycle review is
  M2, not Phase 1. `[CITED: ARCHITECTURE.md]`

## Stale-Research Flags (harvested `.planning/research/` vs live code)

| Harvested claim | Status vs live code | Verdict |
|-----------------|---------------------|---------|
| `ARCHITECTURE.md`: "Do not use the current global exception behavior that returns 200 for every webhook exception" | True and live (`main.py:83-87`) — but fixing it is **M2** (changing webhook error semantics to 5xx-on-DB-failure). D-08 explicitly keeps 200-fast for Phase 1. | **Stale for this phase** — correct long-term, but the planner must NOT change the global handler now. |
| `ARCHITECTURE.md`/`PITFALLS.md`: "require and verify HMAC `X-Hub-Signature-256` before parsing" | `verify_get` has a dormant signature branch (`whatsapp_meta.py:181-186`); `WA_META_APP_SECRET` is optional/unused. | **Out of scope (M2 fence).** Leave the dormant branch dormant. |
| `ARCHITECTURE.md`: "Order creation … replace with one typed transactional RPC" | The current multi-write order insert (`whatsapp.py:278-297`) is non-atomic. | **Out of scope** — D-06 says reuse the existing flow unchanged. M1 Phase elsewhere may address atomicity; not Phase 1. |
| `ARCHITECTURE.md` `MetadataObject.phoneNumberId` (camelCase) in SDK types | The **wire** field is `phone_number_id` (snake_case); the SDK type has a typo/transform. | **Verified wire format is snake_case** — fixtures must use `phone_number_id`. The parser doesn't read metadata, so low-impact, but build fixtures correctly. |
| `PITFALLS.md`: envelope details "MEDIUM confidence … must be validated during M2" | Now **validated** against Meta's own SDK type source. | **Upgraded to HIGH** — confirmed this session. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Running the existing **sync** handler inside an `async def` route (or via `run_in_threadpool`) is acceptable for the smoke-thread per D-08 | Pattern 1 | If the inline block on the event loop causes noticeable latency under real traffic, replies could be slow; but volume is tiny and async worker is M2. Planner picks `run_in_threadpool` vs inline. Low risk. |
| A2 | Expired/invalid Meta token surfaces as HTTP 401 / error code 190 (`OAuthException`) | Pitfall 3 | Wrong code label only; the failure (auth) is real regardless. Cosmetic. |
| A3 | Sending to a non-registered recipient surfaces as delivery error `#131030`/`131026` | Pitfall 5 | Wrong code label only; the symptom (no delivery) is the real signal. Cosmetic. |
| A4 | The smoke-test should delete `orders`+`order_lines`+`sessions` for the test phone; leaving one `customers` row is acceptable low-harm | Runtime State Inventory / D-07 | If retention/PII policy (M1 RET-*) is stricter, the test `customers` row may also need deletion. Confirm cleanup scope with Khaled. |

**If this table is empty:** it is not — these four assumptions need planner/Khaled confirmation, none
block the core code change.

## Open Questions

1. **Sync-in-async dispatch shape (A1).**
   - What we know: D-08 permits inline processing; the handler is sync; `requests`/Supabase calls block.
   - What's unclear: wrap in `run_in_threadpool` vs accept brief inline block.
   - Recommendation: `run_in_threadpool(_handle_message, ...)` — cleanest minimal change, keeps the loop
     responsive, no behavior change to the handler.

2. **Cleanup scope of the live smoke order (A4 / D-07).**
   - What we know: D-07 says delete the one real order; tests must not write to prod.
   - What's unclear: whether to also purge the test `customers`/`chat_history` rows.
   - Recommendation: delete `order_lines` → `orders` → `sessions` for the test phone (FK-safe order);
     decide `customers`/`chat_history` with Khaled (default: leave, note in verification log).

3. **Token type for the proof (D-02).**
   - Recommendation: generate a System User token before the proof so the 24h temp-token clock doesn't
     gate the manual live test.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| FastAPI / uvicorn | webhook route | ✓ | installed | — |
| `requests` | Meta send | ✓ | installed | — |
| Live Supabase project | order write (D-01) | ✓ | project `ppwcfmuetgczclmnzvqr` | — |
| Public HTTPS URL for webhook | Meta inbound delivery | ✓ (Railway `alyasmeen.org`) / tunnel for local | — | ngrok/cloudflared tunnel for local live test |
| **Meta Cloud API token** (`WA_META_TOKEN`) | live send (D-01/D-02) | **✗ — HUMAN PREREQUISITE** | — | **NONE — blocks D-01 completion** |
| **`WA_META_PHONE_ID`** | live send | **✗ — HUMAN PREREQUISITE** | — | **NONE — blocks live send** |
| `WA_META_VERIFY_TOKEN` | webhook GET handshake | partial (env-set) | — | must match Meta config form |
| **Aunt + Khaled registered as ≤5 test recipients** | aunt notification (D-01) | **✗ — HUMAN PREREQUISITE** | — | **NONE — aunt won't receive without it** |

**Missing dependencies with NO fallback (BLOCK phase completion — surface loudly per D-02):**
- Working Meta Cloud API token (`WA_META_TOKEN`) — temp (24h) or System User (~60d/permanent).
- `WA_META_PHONE_ID` (the test/business phone number ID from Meta API Setup).
- Aunt's number + Khaled's number added to Meta's test-recipient allow-list.
- `USE_MOCK_WHATSAPP=0` set in the runtime env **and process restarted** before the proof.

**Missing dependencies with fallback:**
- Local public URL: use a tunnel (ngrok/cloudflared) if not testing against the deployed Railway URL.

### D-02 — Concrete ordered human steps for Khaled (the blocking prerequisite)
```
1. Meta App Dashboard → WhatsApp → API Setup.
   - Note the test "Phone number ID"  → WA_META_PHONE_ID
   - Copy the temporary access token   → WA_META_TOKEN  (EXPIRES IN 24h)
2. Same page → "To" recipient list → add the AUNT's number AND Khaled's number
   (≤5 allowed pre-business-verification). Each must accept the WhatsApp opt-in prompt.
3. (Recommended) Generate a non-expiring token instead of the 24h temp:
   Business Settings → Users → System Users → create admin system user →
   assign the WhatsApp Business Account → Generate token with
   whatsapp_business_messaging + whatsapp_business_management.  → WA_META_TOKEN
4. WhatsApp → Configuration → Webhook:
   - Callback URL: https://alyasmeen.org/whatsapp/webhook  (or tunnel URL)
   - Verify token: paste the SAME string set in env WA_META_VERIFY_TOKEN
   - Subscribe the WABA to the "messages" webhook field.
5. Set runtime env: WA_META_TOKEN, WA_META_PHONE_ID, WA_META_VERIFY_TOKEN, USE_MOCK_WHATSAPP=0
   → RESTART the process (sender binds at import — Pitfall 4).
Failure modes to watch: temp token expiry (Pitfall 3), recipient not registered (Pitfall 5),
verify-token mismatch (Pitfall 6).
```
Sources: `[CITED: developers.facebook.com/docs/whatsapp/cloud-api/get-started]`,
`[CITED: developers.facebook.com/blog/post/2022/12/05/auth-tokens]`, cross-verified via multiple guides.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` → section included.

This phase has **two distinct proof tracks** that must not be conflated:
- **Automated track (SPINE-01 parser):** fast, hermetic, runs in CI; proves the envelope parses and the
  flat path still works. Never touches live Supabase or Meta (D-07).
- **Manual live track (D-01 / SPINE-02):** human-gated by the Meta token; proves the real path lives.
  Cannot be automated and must not write to prod via tests.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (`tests/` , `pytest.ini`) `[VERIFIED: codebase pytest.ini]` |
| Config file | `pytest.ini` — `testpaths = tests`, `addopts = -m "not integration"` |
| Quick run command | `python -m pytest tests/unit/test_whatsapp_meta_envelope.py -x` |
| Full suite command | `python -m pytest` (excludes `integration` marker by default) |
| DB isolation | `tests/conftest.py` autouse `mock_db` monkeypatches `wa.execute`/`wa.execute_returning`/session helpers to in-memory fakes → **no test touches live Supabase** `[VERIFIED: codebase tests/conftest.py:34-52]` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SPINE-01 | Meta text envelope → `(from,text,wa_name)` → handler (no 422) | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_text_message_parses -x` | ❌ Wave 0 |
| SPINE-01 | Meta button_reply `id` → command text → handler branch | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_button_reply_maps_to_command -x` | ❌ Wave 0 |
| SPINE-01 | Meta list_reply `id` parsed (defensive) | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_list_reply_parses -x` | ❌ Wave 0 |
| SPINE-01 | Status callback (delivered) → 200 no-op, handler NOT called | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_status_callback_noop -x` | ❌ Wave 0 |
| SPINE-01 | Unsupported type (image/reaction) → 200 no-op | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_unsupported_type_noop -x` | ❌ Wave 0 |
| SPINE-01 | **Flat dev `Msg` shape still works (regression)** | unit | `pytest tests/unit/test_whatsapp.py -x` (existing) + new flat-shape-via-new-route assert | ✅ existing |
| SPINE-01 | Real envelope POST through `TestClient` returns 200 (not 422) | integration-lite (mock_db) | `pytest tests/integration/test_bot_flow.py -x` (extend) | ✅ extend |
| SPINE-02 | `confirm` from a parsed Meta envelope writes order + notifies aunt (mocked DB/sender) | integration-lite | `pytest tests/integration/test_bot_flow.py::test_meta_envelope_confirm_flow -x` | ❌ Wave 0 |
| SPINE-02 | **Live proof (D-01): real msg → real Supabase row in /orders → aunt phone buzzes** | **manual, human-gated** | `checkpoint:human-verify` (NOT a pytest test — token-gated, writes prod, then D-07 cleanup) | n/a |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/test_whatsapp_meta_envelope.py -x` (parser fixtures)
- **Per wave merge:** `python -m pytest` (full suite, excludes integration marker — proves no regression)
- **Phase gate:** full suite green AND the manual live-proof checkpoint signed off (D-01).

### Live-proof checkpoint (how the manual gate is verified vs the automated test)
The automated parser test proves the *envelope parses*. It deliberately does NOT prove the real path
(D-07 forbids prod writes from tests). The **live proof** is a separate human-gated checkpoint:
1. Confirm D-02 prerequisites met (token, phone ID, recipients, `USE_MOCK_WHATSAPP=0`, restarted).
2. Khaled sends a real WhatsApp message from a registered test number; completes cart → confirm.
3. Verify: (a) no 422 in logs, (b) the order appears in `/orders`, (c) the aunt's phone receives the
   `🛍️ طلب جديد!` notification.
4. **D-07 cleanup:** delete the smoke `order_lines` → `orders` → `sessions` rows for the test phone.
Record evidence (screenshot of /orders + aunt's phone, the captured `wamid`) in the verification log.

### Wave 0 Gaps
- [ ] `tests/data/meta_webhook_text.json` — fixture for SPINE-01 text (D-03)
- [ ] `tests/data/meta_webhook_button_reply.json` — fixture for interactive button
- [ ] `tests/data/meta_webhook_list_reply.json` — fixture for interactive list
- [ ] `tests/data/meta_webhook_status.json` — fixture for status callback (no-op)
- [ ] `tests/unit/test_whatsapp_meta_envelope.py` — parser regression tests (covers SPINE-01)
- [ ] `tests/integration/test_bot_flow.py` — extend with a Meta-envelope→confirm flow (SPINE-02, mocked DB)
- [ ] No framework install needed — pytest already present.

## Security Domain

> `security_enforcement` is not `false` in config → section included, scoped to Phase 1's tiny surface.
> NOTE: most webhook security controls (HMAC signature, rate limiting, auth) are **explicitly M2** per
> the scope fences and are NOT to be built here.

### Applicable ASVS Categories (Phase 1 surface only)
| ASVS Category | Applies | Standard Control (this phase) |
|---------------|---------|-------------------------------|
| V2 Authentication | no | Webhook signature verification is **M2** (deferred). Don't build. |
| V3 Session Management | no | No sessions in the webhook path. |
| V4 Access Control | no | Rate limiting / auth on webhook is **M2**. |
| V5 Input Validation | **yes (light)** | Parser must guard against missing/malformed keys (`.get()` everywhere, no bare indexing) so a malformed POST is a safe 200 no-op, not a crash. This is correctness, not the M2 hardening. |
| V6 Cryptography | no | HMAC `X-Hub-Signature-256` is **M2**. The dormant branch in `verify_get` stays dormant. |

### Known Threat Patterns for this stack (Phase 1 relevant subset)
| Pattern | STRIDE | Standard Mitigation | In/Out of Phase 1 |
|---------|--------|---------------------|-------------------|
| Unauthenticated webhook POST triggers order/spend | Spoofing/Elevation | HMAC signature verify | **OUT — M2.** Documented in PITFALLS; do not build here. |
| Malformed payload crashes parser (DoS-lite) | DoS | Defensive `.get()` parsing, no bare index | **IN** — parser must not raise on bad input (Pitfall 2). |
| SQL injection via message text | Tampering | `%s` placeholders + `_escape()` in `database.py` (already enforced) | Already mitigated; the parsed `text` flows through the existing parameterized path. `[VERIFIED: database.py:45-71]` |
| Customer text treated as instruction (prompt injection) | Tampering | AI path hardening | **OUT — M3.** D-06 keeps the AI path out of the proof. |

**The one security-relevant rule for this phase:** parse defensively (`.get()`, guard indexes) so that
a forged/garbage POST is a harmless 200 no-op rather than a crash — but do NOT add authentication,
signature verification, or rate limiting (all M2). Keep using `%s`/`_escape` for any DB write (unchanged).

## Project Constraints (from CLAUDE.md)
The planner MUST honor these (same authority as locked decisions):
- **HTTPS-RPC only** — DB access via `query`/`execute`/`execute_returning` in `database.py`; no psycopg2,
  no `DATABASE_URL`, no direct `supabase` import elsewhere. (Order write already complies.)
- **One DB file** (`database.py`), **one AI file** (`ai_service.py`) — the parser must not introduce DB
  or AI access; it only normalizes the request.
- **SQL via `%s` only** — never f-strings. (Parser does no SQL; the reused `confirm` path already uses `%s`.)
- **Never hardcode secrets** — use `Config.*` (`WA_META_TOKEN`, etc.). Never commit `.env`.
- **Keep `claude-haiku-4-5`** — irrelevant to this phase (AI path untouched, D-06).
- **No AppSheet** — N/A.
- Update `ALYASMEEN/wiki/*.md` (and `log.md`) after the change so the vault stays current — note the
  webhook parse seam is now Meta-aware.

## Sources

### Primary (HIGH confidence)
- Meta official WhatsApp Node.js SDK type definitions — `github.com/WhatsApp/WhatsApp-Nodejs-SDK`
  `src/types/webhooks.ts` + `src/types/enums.ts` (fetched this session): authoritative
  `WebhookObject`/`Entry_Object`/`ChangesObject`/`ValueObject`/`MessagesObject`/`StatusesObject`/
  `ButtonReplyObject`/`ListReplyObject`/`ContactObject`/`StatusEnum`.
- Codebase (verified by direct read): `app/routers/whatsapp.py` (`Msg` model :165-168, POST seam
  :171-172, send_buttons IDs, confirm flow :262-323, import-time sender bind :29-32),
  `app/services/whatsapp_meta.py` (send_text/send_buttons/verify_get), `app/services/whatsapp_dev.py`,
  `app/db/database.py` (`%s`/`_escape`/`_build`), `app/main.py` (global 200 handler :83-87),
  `tests/conftest.py` (mock_db isolation), `tests/unit/test_whatsapp.py`, `tests/integration/test_bot_flow.py`,
  `app/services/config.py`, `pytest.ini`, `.planning/config.json`.

### Secondary (MEDIUM confidence)
- WebSearch (cross-verified): WhatsApp Cloud API interactive button_reply JSON example (matches SDK
  types); ≤5 test recipients pre-verification; temp token 24h vs System User ~60d/permanent.
- `https://developers.facebook.com/blog/post/2022/12/05/auth-tokens/` (token lifetimes).

### Tertiary (LOW confidence — flagged in Assumptions)
- Exact Meta error codes for token expiry (190/OAuthException) and unregistered recipient
  (#131030/#131026) — symptom is verified, code label is assumed (A2/A3).

### Harvested (reference, partially stale — see Stale-Research Flags)
- `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md`, `.planning/codebase/CONCERNS.md`.

## Metadata

**Confidence breakdown:**
- Meta envelope schema: HIGH — verified against Meta's own SDK type source this session.
- Codebase seam analysis: HIGH — every claim cites a read line.
- Interactive reply mapping: HIGH — reply IDs verified to equal handler command strings in-repo.
- Token/recipient setup: MEDIUM-HIGH — official docs + multiple cross-verified guides; exact error codes LOW.
- Live-proof gating: HIGH — driven by binding D-01/D-02 decisions.

**Research date:** 2026-06-15
**Valid until:** ~2026-07-15 for the envelope schema (stable, Meta envelope unchanged since 2022).
Token/portal UI steps may drift (~2 weeks) as Meta updates the developer console; re-verify the D-02
click-path if it looks different.

## RESEARCH COMPLETE
