"""
tests/eval/conftest.py — guards and fixtures specific to the agent eval.

Two independent things happen here:

1. A hard opt-in guard (`_eval_guard`, autouse) on top of pytest's marker-based exclusion in
   pyproject.toml (`addopts = '-m "not integration and not eval"'`). Belt and suspenders: the
   marker keeps `pytest -q` / `pytest tests/` from ever collecting real API spend by default;
   this fixture additionally refuses to run even a deliberate `pytest -m eval tests/eval`
   invocation unless `RUN_AGENT_EVAL=1` AND a real `CLAUDE_API_KEY` is configured — so nobody
   burns API cost by accident just by typing the right marker flag.

2. `eval_catalog` (autouse) — makes the product catalog immune to both the 60s TTL
   (`app.ai.retriever.CATALOG_TTL_SECONDS`) and the live-DB guard for the whole length of a
   real-API eval run. See the fixture's own docstring for why patching just the cache is not
   enough.

`tests/conftest.py`'s own autouse fixtures (`block_live_db`, `mock_db`, plus the `fake_db`,
`sent_messages`, `flush_outbox` fixtures) already apply here — pytest fixtures cascade down
from a parent conftest.py to every test under it, so nothing needs re-declaring for the DB/
WhatsApp-sender seams. `generate_reply()` itself is deliberately never patched anywhere in
this tree — the eval's whole point is a real Claude call through the real pipeline.
"""
from __future__ import annotations

import os

import pytest

from app.services.config import Config

# 8 ALYASMEEN-style products (creams, lotions, candles), Arabic names, numeric-string `sku`
# values — whatsapp_helpers.catalog() does `int(r["sku"])` and silently skips rows that fail
# (whatsapp_helpers.py:29-33), so a non-numeric sku here would just vanish from the AI's
# grounded catalog with no error.
EVAL_CATALOG: list[dict] = [
    {
        "sku": "1", "name": "كريم اليدين الطبيعي", "price": 35.0,
        "description": "كريم مرطب للأيدي بزيت الزيتون وزبدة الشيا، مناسب للبشرة الجافة",
        "tags": ["كريم", "creams", "يدين", "hand cream"], "aliases": "hand cream",
    },
    {
        "sku": "2", "name": "كريم الجسم بالخزامى", "price": 45.0,
        "description": "كريم جسم طبيعي 100% برائحة اللافندر",
        "tags": ["كريم", "creams", "جسم", "body cream"], "aliases": "body cream, lavender cream",
    },
    {
        "sku": "3", "name": "شمعة اللافندر", "price": 30.0,
        "description": "شمعة طبيعية بريحة اللافندر مصنوعة يدوياً",
        "tags": ["شموع", "candles"], "aliases": "lavender candle",
    },
    {
        "sku": "4", "name": "شمعة الورد", "price": 30.0,
        "description": "شمعة طبيعية برائحة الورد الدمشقي",
        "tags": ["شموع", "candles"], "aliases": "rose candle",
    },
    {
        "sku": "5", "name": "مطري الشعر الطبيعي", "price": 40.0,
        "description": "مطري شعر بزيت الأرغان، يرطب ويلمّع الشعر",
        "tags": ["شعر", "hair", "مطري"], "aliases": "hair conditioner, hair softener",
    },
    {
        "sku": "6", "name": "شامبو الأعشاب الطبيعي", "price": 38.0,
        "description": "شامبو طبيعي بخلاصة الأعشاب لتقوية الشعر",
        "tags": ["شعر", "hair", "شامبو"], "aliases": "shampoo",
    },
    {
        "sku": "7", "name": "لوشن الجسم بزبدة الشيا", "price": 42.0,
        "description": "لوشن مرطب خفيف بزبدة الشيا الطبيعية",
        "tags": ["لوشن", "lotion", "جسم"], "aliases": "body lotion",
    },
    {
        "sku": "8", "name": "مقشر الجسم الطبيعي", "price": 33.0,
        "description": "مقشر طبيعي للجسم بحبيبات السكر وزيت اللوز",
        "tags": ["مقشر", "exfoliator", "جسم"], "aliases": "body scrub, exfoliator",
    },
]


@pytest.fixture(autouse=True)
def _eval_guard():
    """Refuse to run anything under tests/eval/ unless explicitly opted in.

    Marker-based exclusion (pyproject.toml) already keeps this out of every default or
    accidental pytest invocation; this is the second, independent guard for the case someone
    runs `pytest -m eval tests/eval` on purpose but without meaning to spend real API money
    right now.
    """
    if os.environ.get("RUN_AGENT_EVAL") != "1":
        pytest.skip(
            "Agent eval makes real Claude API calls and costs money — "
            "set RUN_AGENT_EVAL=1 to run it deliberately."
        )
    if not Config.CLAUDE_API_KEY:
        pytest.skip("Agent eval requires CLAUDE_API_KEY to be configured.")


@pytest.fixture(autouse=True)
def eval_catalog(monkeypatch):
    """Make the catalog immune to both the TTL and the live DB for the whole run.

    Patching `_load_catalog` (not just `_CATALOG`/`_CATALOG_LOADED_AT`) means every TTL expiry
    during a long real-API run still resolves through this fixture instead of falling through
    to the real, blocked, database call. `app.ai.retriever._catalog()` re-checks the TTL on
    every call (`_CATALOG is None or (time.monotonic() - _CATALOG_LOADED_AT) >
    CATALOG_TTL_SECONDS`, 60s) — a full 75-case run against the real Claude API takes well over
    60s of wall-clock time, so without this, the back half of a full run would silently see an
    EMPTY catalog: under `block_live_db`, the reload hits the blocked live-DB guard, and
    `ai_service._full_catalog_context()` swallows that exception and returns `""`.

    Works for every catalog consumer without any extra patching: `ai_service` imports
    `_catalog` inside the function body (late binding, sees the patch immediately), and
    `whatsapp_helpers.catalog()`/`processor.catalog` bound the same function OBJECT at import
    time — but that object's own body still does a fresh module-global lookup of
    `_load_catalog` on every cache-miss/TTL-expiry, so patching the module attribute here
    reaches all three callers through the one real `_catalog()` function.
    """
    import app.ai.retriever as retriever

    monkeypatch.setattr(retriever, "_load_catalog", lambda: EVAL_CATALOG)
    retriever.invalidate_catalog()  # drop any stale cache; next _catalog() call re-primes via the patched loader
    yield
    retriever.invalidate_catalog()
