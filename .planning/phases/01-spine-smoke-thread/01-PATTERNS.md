# Phase 1: Spine Smoke-Thread - Pattern Map

**Mapped:** 2026-06-15
**Files analyzed:** 4 (1 modified, 3 created) + 1 extended test
**Analogs found:** 4 / 4 (all in-repo, exact or strong role matches)

> This is a brownfield **seam fix**, not a build. Every new file has a close in-repo
> analog. The planner should copy the cited excerpts almost verbatim and adjust only
> the payload shape. There is **no need to fall back to RESEARCH.md generic patterns** —
> the codebase already contains a working webhook route, a DB-isolation harness, a
> TestClient integration suite, and the reply-ID vocabulary the parser must mirror.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/routers/whatsapp.py` (MODIFY `webhook_post` seam + add `_parse_meta_envelope`) | route / handler | request-response (webhook ingress → transform → dispatch) | itself (`webhook_get` at `:154-162` for raw-`Request` access; `webhook_post` at `:171-486` for the handler body to preserve) | exact (in-file) |
| `tests/data/meta_webhook_text.json` | test fixture | data (static envelope sample) | `tests/data/whatsapp_agent_dataset.json` (existing JSON fixture under `tests/data/`) | role-match |
| `tests/data/meta_webhook_button_reply.json` | test fixture | data | same | role-match |
| `tests/data/meta_webhook_list_reply.json` | test fixture | data | same | role-match |
| `tests/data/meta_webhook_status.json` | test fixture | data | same | role-match |
| `tests/unit/test_whatsapp_meta_envelope.py` (CREATE) | test (unit, pure-function) | transform (envelope dict → tuples) | `tests/unit/test_whatsapp_helpers.py` (pure import + direct call) and `tests/unit/test_whatsapp_meta.py::TestVerifyGet` (no-TestClient unit style) | exact (role + flow) |
| `tests/integration/test_bot_flow.py` (EXTEND) | test (integration, TestClient) | request-response (POST → 200 + order) | itself (`TestFullPickupOrderFlow`, `TestAuntNotification`) | exact (in-file) |

> **Filename caution:** a `tests/unit/test_whatsapp_meta.py` already exists (covers
> `whatsapp_meta.py` sender/verify_get). The new parser test MUST be named
> `test_whatsapp_meta_envelope.py` (per RESEARCH.md / Wave-0 gaps) so it does not collide.

---

## Pattern Assignments

### `app/routers/whatsapp.py` — MODIFY the POST seam (route / request-response)

**Analog:** itself — `webhook_get` shows the raw-`Request` + async pattern already used in this file; `webhook_post` is the handler body to preserve. `Request` is **already imported** (`whatsapp.py:6`), so no new import is needed for the seam.

**The exact seam being changed** (`whatsapp.py:165-172`) — this is the bug. FastAPI validates the body against `Msg` before any code runs, so a nested Meta envelope 422s:
```python
class Msg(BaseModel):
    from_number: str
    text: str
    wa_name: str | None = None  # WhatsApp profile name (sent by Meta API)


@router.post("/webhook")
def webhook_post(msg: Msg):
    phone = msg.from_number
    text = (msg.text or "").strip()
    low = text.lower()
    wa_name = (msg.wa_name or "").strip()
    ...  # 300+ lines of handler logic, lines 178-486 — DO NOT touch
```

**Raw-`Request` + async access pattern to copy** — the sibling GET route in the same file already does exactly this (it reads `request.query_params` instead of binding a model):
```python
# whatsapp.py:154-162  (the in-file precedent for accepting a raw Request)
@router.get("/webhook")
async def webhook_get(request: Request):
    params = dict(request.query_params)
    try:
        ok, code, body = verify_get(params)
        return PlainTextResponse(content=body) if code == 200 else (body, code)
    except TypeError:
        ok, code, body = verify_get(params, dict(request.headers), b"")
        return PlainTextResponse(content=body) if code == 200 else (body, code)
```

**Recommended seam shape (RESEARCH.md Pattern 1 + this file's `webhook_get` style):**
The handler body (`whatsapp.py:178-486`) consumes exactly four locals: `phone`, `text`, `low`, `wa_name` (set at `:173-176`). The minimal-blast-radius edit is to extract that body into `_handle_message(phone: str, text: str, wa_name: str | None)` and make the route a thin dispatcher:
```python
@router.post("/webhook")
async def webhook_post(request: Request):
    body = await request.json()

    # --- Meta Cloud API envelope (nested) ---
    if body.get("object") == "whatsapp_business_account":
        results = []
        for from_number, text, wa_name in _parse_meta_envelope(body):
            results.append(_handle_message(from_number, text, wa_name))
        return {"ok": True}  # 200 even with zero actionable msgs (status cb / unsupported)

    # --- Flat dev/mock shape (KEEP — tests + mock sender depend on it) ---
    from_number = body.get("from_number", "")
    text = body.get("text", "")
    wa_name = body.get("wa_name")
    return _handle_message(from_number, text, wa_name)
```
- `_handle_message` is the **verbatim** current body of `webhook_post` (`whatsapp.py:178-486`), with its first 4 lines becoming the function parameters. **No order/confirm/notify logic changes** (D-04/D-06).
- **A1 (sync-in-async):** the body calls blocking `requests.post` + Supabase RPC. RESEARCH.md recommends `run_in_threadpool(_handle_message, ...)` to keep the loop responsive; inline is also acceptable per D-08. Planner picks one — `from starlette.concurrency import run_in_threadpool` if wrapping.

**The pure parser helper to add** (keep it pure → unit-testable without TestClient; mirrors the `.get()`-everywhere defensive style already in this file's tool handlers):
```python
# Add to whatsapp.py (or whatsapp_helpers.py). Defensive .get() throughout — a malformed
# POST must be a harmless 200 no-op, never a crash (RESEARCH Pitfall 2 / V5 input validation).
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
            if not messages:                      # status callback / no inbound → ignore
                continue
            contacts = value.get("contacts") or []
            wa_name = contacts[0].get("profile", {}).get("name") if contacts else None
            for m in messages:
                frm = m.get("from", "")
                mtype = m.get("type")
                if mtype == "text":
                    text = (m.get("text") or {}).get("body", "")
                elif mtype == "interactive":
                    inter = m.get("interactive") or {}
                    sub = inter.get("type")        # "button_reply" | "list_reply"
                    text = (inter.get(sub) or {}).get("id", "") if sub else ""
                else:
                    continue                       # media/reaction/etc → ignore (D-05)
                if frm and text:
                    out.append((frm, text, wa_name))
    return out
```

**Interactive reply → command IDENTITY map (D-05, why it's nearly free):**
The parser maps `interactive.{type}.id` → text directly because `send_buttons` in this very file emits reply IDs that **are** the handler's command strings. The handler then branches on them unchanged:

| Reply `id` emitted by `send_buttons` | Emitting line(s) in `whatsapp.py` | Consumed by handler branch |
|--------------------------------------|-----------------------------------|----------------------------|
| `confirm`  | `:224, :258, :338` | `if low == "confirm"` (`:262`) |
| `clear`    | `:225, :229`       | `if low == "clear"` (`:232`) |
| `pickup`   | `:227, :382, :408` | `if low in ("pickup","delivery")` (`:239`) |
| `delivery` | `:228, :338-339, :383, :409` | same (`:239`) |
| `cart`     | `:226, :384, :410` | `if low == "cart"` (`:206`) |

Confirmed emission shape (`whatsapp.py:223-229`) — note `id` is the bare command word:
```python
return send_buttons(phone, cart_text,
    [{"id": "confirm", "title": "✅ تأكيد الطلب"},
     {"id": "clear",   "title": "🗑️ مسح السلة"}])
...
return send_buttons(phone, "تمام، استلام من المتجر ✅",
    [{"id": "confirm", "title": "✅ تأكيد الطلب"}])
```
So `interactive.button_reply.id == "confirm"` flows straight into the existing confirm branch with **no new command vocabulary**. `list_reply` is defensive-only this phase (the menu is plain `send_text` numbers, `whatsapp.py:359`) — still parse it so a future list menu works.

**DO NOT touch (verbatim reuse, cited):**
- Order insert + lines + order_name update — `whatsapp.py:278-297` (`execute_returning` / `execute`, `%s` only).
- Aunt notification block — `whatsapp.py:302-321` (already wrapped in try/except; only fires when `Config.AUNT_PHONE` set).
- The import-time sender bind — `whatsapp.py:29-32` (flipping `USE_MOCK_WHATSAPP` needs a process restart, Pitfall 4).

---

### `tests/data/meta_webhook_*.json` — CREATE 4 fixtures (test fixture / static data)

**Analog:** `tests/data/whatsapp_agent_dataset.json` — establishes the convention that committed JSON test data lives under `tests/data/`. (It is a flat list of labeled messages; the new fixtures are single Meta-envelope dicts — same directory, same role.)

Build each fixture **verbatim from the verified schema in `01-RESEARCH.md`** (snake_case wire fields — `phone_number_id`, not camelCase):
- `meta_webhook_text.json` ← RESEARCH.md lines 424-444 (TEXT). Expect parse → `("972599123456", "menu", "فاطمة")`.
- `meta_webhook_button_reply.json` ← RESEARCH.md lines 454-470 (`interactive.button_reply.id == "confirm"`). Expect → `("972599123456", "confirm", "فاطمة")`.
- `meta_webhook_list_reply.json` ← RESEARCH.md lines 477-481 (`list_reply.id == "prod_1"`), wrapped in the full envelope. Expect → text `"prod_1"` (defensive).
- `meta_webhook_status.json` ← RESEARCH.md lines 487-499 (`value.statuses[]`, NO `messages`). Expect parse → `[]` (200 no-op).

These are static JSON files — **use the Write tool**, not a Pydantic model, not heredoc.

---

### `tests/unit/test_whatsapp_meta_envelope.py` — CREATE (test, unit, pure-function transform)

**Analog:** `tests/unit/test_whatsapp_helpers.py` (direct import + call, no TestClient) and `tests/unit/test_whatsapp_meta.py::TestVerifyGet` (plain `assert` on a returned tuple). The parser is a pure function → test it directly against the fixtures; **no DB, no TestClient, no `mock_db` needed** (though `conftest.mock_db` is autouse and harmless).

**Direct-import + class-grouping convention to copy** (from `test_whatsapp_meta.py:10-24`):
```python
class TestVerifyGet:
    def test_valid_token_returns_200_with_challenge(self, monkeypatch):
        import app.services.whatsapp_meta as meta
        ...
        ok, code, body = meta.verify_get({...})
        assert ok is True
        assert code == 200
```

**Fixture-loading helper to add** (no existing test loads JSON yet — establish the smallest pattern using `pathlib`, mirroring the `ROOT = Path(__file__).resolve().parents[N]` idiom already in `test_whatsapp.py:16` and `test_bot_flow.py:16`):
```python
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"   # tests/data

def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))
```

**Tests to write (one per Validation-Architecture row, RESEARCH.md lines 655-659):**
```python
from app.routers.whatsapp import _parse_meta_envelope   # adjust if helper lands in whatsapp_helpers

class TestMetaEnvelopeParser:
    def test_text_message_parses(self):
        out = _parse_meta_envelope(_load("meta_webhook_text.json"))
        assert out == [("972599123456", "menu", "فاطمة")]

    def test_button_reply_maps_to_command(self):
        out = _parse_meta_envelope(_load("meta_webhook_button_reply.json"))
        assert out[0][1] == "confirm"          # id IS the command

    def test_list_reply_parses(self):
        out = _parse_meta_envelope(_load("meta_webhook_list_reply.json"))
        assert out[0][1] == "prod_1"

    def test_status_callback_noop(self):
        assert _parse_meta_envelope(_load("meta_webhook_status.json")) == []

    def test_unsupported_type_noop(self):
        body = {"object": "whatsapp_business_account", "entry": [{"changes": [
            {"field": "messages", "value": {"messages": [
                {"from": "9725991", "type": "image", "image": {"id": "x"}}]}}]}]}
        assert _parse_meta_envelope(body) == []

    def test_malformed_payload_is_safe(self):
        assert _parse_meta_envelope({}) == []   # no crash on garbage (V5)
```
Run per task: `python -m pytest tests/unit/test_whatsapp_meta_envelope.py -x`.

---

### `tests/integration/test_bot_flow.py` — EXTEND (test, integration, TestClient)

**Analog:** itself — `TestFullPickupOrderFlow.test_complete_pickup_order` (`:60-94`) and `TestAuntNotification` (`:128-150`). Copy the file's header boilerplate, `client` fixture, and assertion style exactly.

**TestClient + module-import boilerplate already at top of file (`:8-39`) — reuse, do not duplicate:**
```python
os.environ["USE_MOCK_WHATSAPP"] = "1"
import app.routers.whatsapp as wa
from app.main import app
FAKE_CATALOG = [{"id": 1, "name": "كريم اليدين", "list_price": 25.0, ...}, ...]

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(wa, "_CATALOG", FAKE_CATALOG)
    return TestClient(app)
```

**The flat-shape POST pattern the new route MUST keep passing (regression anchor, `test_bot_flow.py:66`):**
```python
r1 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
assert r1.status_code == 200
```
Every existing test posts this exact flat dict (no `object` key) → the new shape-detection branch routes it down the dev/mock path. This is the SPINE-01 regression guarantee.

**Aunt-notification capture pattern to reuse for the SPINE-02 confirm assertion (`test_bot_flow.py:129-150`):**
```python
def test_aunt_notified_on_confirm(self, client, monkeypatch):
    import app.services.config as config_mod
    monkeypatch.setattr(config_mod.Config, "AUNT_PHONE", "972591111111")
    sent_to = []
    monkeypatch.setattr(wa, "send_text", lambda to, msg: sent_to.append(to) or {"dev": True})
    ... # drive the flow
    assert "972591111111" in sent_to
```

**New test to add — `test_meta_envelope_confirm_flow` (SPINE-02, mocked DB via autouse `mock_db`):**
Drive the cart→confirm flow but POST a **Meta envelope** for the final `confirm` step (built like `meta_webhook_button_reply.json`, but its inner sub-flow can use the flat shape to seed the cart, since shape detection is per-request). Assert: (a) `r.status_code == 200` (NOT 422 — the core bug), (b) the parsed confirm reaches the handler and the order is created / aunt captured. Example skeleton:
```python
class TestMetaEnvelopeFlow:
    def test_meta_envelope_confirm_flow(self, client, monkeypatch):
        phone = "972599123456"
        # seed cart + pickup via flat dev shape (allowed; per-request shape detect)
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
        client.post("/whatsapp/webhook", json={"from_number": phone, "text": "pickup"})
        # confirm via a real Meta button_reply envelope (id == "confirm")
        envelope = {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"field": "messages", "value": {
                "contacts": [{"profile": {"name": "فاطمة"}, "wa_id": phone}],
                "messages": [{"from": phone, "type": "interactive",
                              "interactive": {"type": "button_reply",
                                              "button_reply": {"id": "confirm", "title": "✅"}}}]}}]}],
        }
        r = client.post("/whatsapp/webhook", json=envelope)
        assert r.status_code == 200          # not 422 → SPINE-01 fixed
```
> Note the response shape: when the route loops `_parse_meta_envelope`, it returns `{"ok": True}` (not the handler's `{"ok": True, "order_id": ...}`). If the test needs the order_id, assert on the captured `send_text` to the aunt instead, or have the route surface the last handler result. Planner decides the return contract — but **all `/whatsapp/*` paths must stay 200** (`main.py:83-87`).

---

## Shared Patterns

### DB isolation (autouse — every test inherits it)
**Source:** `tests/conftest.py:11-52`
**Apply to:** both new/extended test files (no opt-in needed; it's `autouse=True`).
The `mock_db` fixture monkeypatches `wa.execute` / `wa.execute_returning` / session + customer helpers to in-memory fakes, so **no test touches live Supabase** (satisfies D-07). `fake_execute_returning` returns an incrementing `{"id": n}` so `confirm` produces `ORD-000n`:
```python
@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    import app.routers.whatsapp as wa
    _order_seq = [0]
    def fake_execute_returning(sql, params=()):
        _order_seq[0] += 1
        return {"id": _order_seq[0]}
    monkeypatch.setattr(wa, "execute_returning", fake_execute_returning)
    monkeypatch.setattr(wa, "execute", lambda sql, params=(): None)
    monkeypatch.setattr(wa, "upsert_customer", lambda phone, name="": False)
    ...  # load_session/save_session/clear_session/get_latest_order all faked
```
**Implication for the seam extraction:** the fixture patches names **on the `wa` module** (e.g. `wa.execute_returning`). If `_handle_message` is defined in `whatsapp.py` it keeps using those module-level names → fixture still works unchanged. If the parser is moved to `whatsapp_helpers.py`, keep `_handle_message` and all DB calls in `whatsapp.py` so the existing isolation holds.

### Defensive parsing (V5 input validation — the one security rule this phase)
**Source:** the `.get()`-everywhere style already in this file's tool handlers (e.g. `whatsapp.py:57-58, 82, 119-123`) and `_parse_meta_envelope` above.
**Apply to:** the parser only. Guard every index/key (`body.get("entry", []) or []`, `value.get("messages")` presence check before iterating) so a forged/garbage/status POST is a harmless 200 no-op, never a `KeyError`/`IndexError` (Pitfall 2). Do **NOT** add HMAC signature verification, rate limiting, or auth — all explicitly M2.

### Response semantics (anti-retry-storm)
**Source:** `app/main.py:83-87` (global handler forces 200 on `/whatsapp/*`).
**Apply to:** the route's return on every branch — text, interactive, status no-op, unsupported, and malformed all return 200. Leave the global handler **unchanged** (D-08; changing it to 5xx-on-DB-failure is M2, flagged stale-for-this-phase in RESEARCH.md).

### Outbound send (reuse, never rebuild)
**Source:** `app/services/whatsapp_meta.send_text` (`:10-39`) / `send_buttons` (`:41-78`); mock `app/services/whatsapp_dev.py`.
**Apply to:** the live proof only. Code already imports the right sender at module load (`whatsapp.py:29-32`). For the D-01 live proof set `USE_MOCK_WHATSAPP=0` **and restart** (Pitfall 4). No sender code changes this phase.

---

## No Analog Found

None. Every new file maps to a strong in-repo analog. The planner should **not** import RESEARCH.md's generic/Node-SDK skeletons except as the source-of-truth for fixture JSON field names (which RESEARCH.md already verified against Meta's SDK).

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | All four new files have exact or strong in-repo analogs. |

---

## Manual (non-automatable) work — surface loudly (D-01 / D-02)

Not a file pattern, but the planner MUST emit these as explicit, blocking tasks (a `checkpoint:human-verify`), because the phase is NOT done on green tests alone (D-01):
- **D-02 (BLOCKS completion):** Khaled obtains a working Meta Cloud API token (`WA_META_TOKEN`) + `WA_META_PHONE_ID`, registers the aunt + himself as ≤5 test recipients, configures the webhook callback URL + verify token, sets `USE_MOCK_WHATSAPP=0`, and **restarts**. Concrete click-path in RESEARCH.md lines 610-629. Prefer a System User token (Pitfall 3 — temp token expires in 24h).
- **Live proof:** real message → no 422 → real `orders`/`order_lines` row visible in `/orders` → aunt's phone receives `🛍️ طلب جديد!`.
- **D-07 cleanup:** after proof, delete the smoke `order_lines` → `orders` → `sessions` rows for the test phone (FK-safe order). Decide `customers`/`chat_history` retention with Khaled (A4).

---

## Metadata

**Analog search scope:** `app/routers/` (whatsapp.py, helpers), `app/services/` (whatsapp_meta, whatsapp_dev, config), `app/main.py`, `tests/` (conftest, unit/, integration/, data/), `pytest.ini`.
**Files scanned:** 9 read in full + `tests/` tree enumerated.
**Pattern extraction date:** 2026-06-15
