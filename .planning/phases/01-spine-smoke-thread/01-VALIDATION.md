---
phase: 1
slug: spine-smoke-thread
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-15
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Two distinct proof tracks (do NOT conflate):
> - **Automated track (SPINE-01 parser):** fast, hermetic, CI-safe. Never touches live Supabase or Meta (D-07).
> - **Manual live track (D-01 / SPINE-02):** human-gated by the Meta token. Cannot be automated; must not write to prod via tests.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing — `tests/`, `pytest.ini`) |
| **Config file** | `pytest.ini` — `testpaths = tests`, `addopts = -m "not integration"` |
| **Quick run command** | `python -m pytest tests/unit/test_whatsapp_meta_envelope.py -x` |
| **Full suite command** | `python -m pytest` (excludes `integration` marker by default) |
| **DB isolation** | `tests/conftest.py` autouse `mock_db` monkeypatches `wa.execute` / `wa.execute_returning` / session helpers to in-memory fakes → no test touches live Supabase |
| **Estimated runtime** | ~5–15 seconds (unit) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/test_whatsapp_meta_envelope.py -x`
- **After every plan wave:** Run `python -m pytest` (full suite — proves no regression in the flat path)
- **Before phase gate:** Full suite green **AND** the manual live-proof checkpoint (D-01) signed off
- **Max feedback latency:** ~15 seconds (automated track)

---

## Per-Task Verification Map

> Task IDs are assigned by the planner. Rows below are keyed by requirement + behavior so the
> planner can attach each to its task. Threat refs come from the PLAN.md `<threat_model>`.

| Requirement | Behavior | Test Type | Automated Command | File Exists |
|-------------|----------|-----------|-------------------|-------------|
| SPINE-01 | Meta text envelope → `(from, text, wa_name)` → handler (no 422) | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_text_message_parses -x` | ❌ W0 |
| SPINE-01 | Meta `button_reply.id` → command text → handler branch | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_button_reply_maps_to_command -x` | ❌ W0 |
| SPINE-01 | Meta `list_reply.id` parsed (defensive) | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_list_reply_parses -x` | ❌ W0 |
| SPINE-01 | Status callback (delivered) → 200 no-op, handler NOT called | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_status_callback_noop -x` | ❌ W0 |
| SPINE-01 | Unsupported type (image/reaction) → 200 no-op | unit | `pytest tests/unit/test_whatsapp_meta_envelope.py::test_unsupported_type_noop -x` | ❌ W0 |
| SPINE-01 | Flat dev `Msg` shape still works (regression) | unit | `pytest tests/unit/test_whatsapp.py -x` (existing) + new flat-shape-via-new-route assert | ✅ existing |
| SPINE-01 | Real envelope POST via `TestClient` returns 200 (not 422) | integration-lite (mock_db) | `pytest tests/integration/test_bot_flow.py -x` (extend) | ✅ extend |
| SPINE-02 | `confirm` from a parsed Meta envelope writes order + notifies aunt (mocked DB/sender) | integration-lite | `pytest tests/integration/test_bot_flow.py::test_meta_envelope_confirm_flow -x` | ❌ W0 |
| SPINE-02 | Live proof (D-01): real msg → real Supabase row in `/orders` → aunt phone buzzes | manual, human-gated | `checkpoint:human-verify` (NOT pytest — token-gated, writes prod, then D-07 cleanup) | n/a |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/data/meta_webhook_text.json` — fixture for SPINE-01 text message (D-03)
- [ ] `tests/data/meta_webhook_button_reply.json` — fixture for interactive button reply
- [ ] `tests/data/meta_webhook_list_reply.json` — fixture for interactive list reply
- [ ] `tests/data/meta_webhook_status.json` — fixture for status callback (no-op)
- [ ] `tests/unit/test_whatsapp_meta_envelope.py` — parser regression tests (covers SPINE-01)
- [ ] `tests/integration/test_bot_flow.py` — extend with a Meta-envelope → confirm flow (SPINE-02, mocked DB)
- [ ] No framework install needed — pytest already present.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live spine proof: real WhatsApp message → real order in `/orders` → aunt's phone receives `🛍️ طلب جديد!` notification via real Meta sender | SPINE-02 / D-01 | Token-gated (D-02), writes to live Supabase, sends a real WhatsApp message — cannot run in CI and must not write prod from tests (D-07) | 1. Confirm D-02 prereqs (working token, `WA_META_PHONE_ID`, aunt+Khaled registered as test recipients, `USE_MOCK_WHATSAPP=0`, app restarted). 2. Khaled sends a real WhatsApp message from a registered test number; completes cart → confirm. 3. Verify (a) no 422 in logs, (b) order appears in `/orders`, (c) aunt's phone receives the notification. 4. **D-07 cleanup:** delete the smoke `order_lines` → `orders` → `sessions` rows for the test phone. Record evidence (screenshots of `/orders` + aunt's phone, captured `wamid`) in the verification log. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (4 fixtures + 1 unit test file + 1 integration extension)
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] Manual live-proof checkpoint (D-01) explicitly planned as a human-gated task that can block phase completion
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
