# Testing

**Analysis Date:** 2026-06-13

## Framework

- **pytest** (test runner) + **FastAPI `TestClient`** (Starlette/httpx) for HTTP-level tests
- Coverage via **coverage.py** — `fail_under = 85` (`pyproject.toml`)
- No separate assertion lib; plain `assert` statements

## Configuration

`pytest.ini`:
```ini
[pytest]
markers =
    integration: marks tests that hit real external services (use with caution)
testpaths = tests
python_files = test_*.py
norecursedirs = scripts .venv .git __pycache__
addopts = -m "not integration"
```
- **Integration tests are excluded by default** (`-m "not integration"`) — run explicitly with `pytest -m integration`
- `pyproject.toml` also declares `[tool.pytest.ini_options] testpaths = ["tests"]`
- Coverage: `source = ["app"]`, omits `app/main.py` and `*/tests/*`

## Structure

```
tests/
├── conftest.py                 # autouse mock_db fixture (in-memory session/history/order)
├── unit/                       # fast, fully mocked
│   ├── test_whatsapp.py        # hard commands, cart, order, address flow
│   ├── test_whatsapp_helpers.py
│   ├── test_whatsapp_meta.py
│   ├── test_ai_service.py
│   ├── test_retriever.py
│   ├── test_database.py
│   ├── test_config.py
│   ├── test_constants.py
│   ├── test_followup.py
│   ├── test_monthly_report.py
│   ├── test_retry.py
│   ├── test_retry_actions_pdf.py
│   ├── test_pdf_invoice.py
│   ├── test_gatekeeper.py
│   └── test_debug.py
├── integration/                # marked @integration (skipped by default)
│   ├── test_bot_flow.py
│   ├── test_orders_api.py
│   └── test_ui_api.py
├── data/                       # eval datasets + generators
│   ├── whatsapp_agent_dataset.json        # 75 labeled customer messages (intent/entities/edge-case tags)
│   ├── whatsapp_agent_dataset_noisy.json
│   ├── eval_intent.py
│   └── generate_noise_dataset.py
└── (legacy top-level) test_whatsapp_ai_aunt.py, test_whatsapp_cart.py,
    test_whatsapp_info.py, test_whatsapp_order.py
```

## Mocking Strategy

**`conftest.py` provides an autouse `mock_db` fixture** — the keystone of the test suite:
- Replaces `whatsapp.py`'s DB-backed helpers with **in-memory dicts** so tests never touch
  real Supabase, and session state persists across requests within a test
- Monkeypatches on the `app.routers.whatsapp` module: `load_session`, `save_session`,
  `clear_session`, `load_history`, `append_history`, `upsert_customer`, `get_customer_name`,
  `get_saved_address`, `save_customer_address`, `get_latest_order`, `execute_returning`, `execute`
- `fake_execute_returning` returns an incrementing fake order id

**Per-test patterns:**
- `os.environ["USE_MOCK_WHATSAPP"] = "1"` set at import time → bot uses `whatsapp_dev` sender
  (mock responses returned as JSON `{"text": ...}` / button payloads, assertable in tests)
- `monkeypatch.setattr(wa, "_CATALOG", FAKE_CATALOG)` injects a fixed catalog
- AI tests mock the Anthropic client / `ai_service.generate_reply` to avoid real API calls
- Random phone numbers (`_phone()`) keep tests isolated

## Test Style

- **Class-grouped tests** (`class TestHardCommands:`) grouping related behaviors
- **Behavioral / black-box** — assert on HTTP responses and Arabic message substrings
  (e.g. `assert "فارغة" in r.json()["text"]`) rather than internals
- **Multi-step flows** — chain `client.post(...)` calls to simulate a conversation
  (menu → select → cart → confirm)

## Running Tests

```bash
pytest                      # unit tests only (integration excluded by default)
pytest -m integration      # integration tests (hit real services — use with caution)
pytest --cov=app           # with coverage (target 85%)
pytest tests/unit/test_whatsapp.py -v
```

## Coverage & Gaps

- Target **85%** enforced via `fail_under`
- Strong coverage of bot hard-commands, cart, retriever, helpers, services
- **Known gaps** (see `CONCERNS.md`): no test exercises the *real* Meta webhook envelope
  shape (tests use the flat `Msg` model), the missing `monthly_snapshots` table, or
  dashboard login brute-force protection

---

*Testing analysis: 2026-06-13*
