# Code Conventions

**Analysis Date:** 2026-06-13

## Language & Style

- **Python 3.10+** (`requires-python = ">=3.10"`, runtime pinned 3.11.9)
- **`from __future__ import annotations`** at top of most modules — deferred annotation evaluation
- **Modern union syntax:** `str | None`, `list[dict[str, Any]]` (PEP 604/585), not `Optional`/`List`
- **Type hints** on public function signatures and most helpers
- **Line length:** 100 chars (ruff `line-length = 100`; `E501` ignored — enforced loosely)

## Linting (ruff)

Configured in `pyproject.toml`:
```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM"]
ignore = ["E501"]
```
- `I` (isort) — imports sorted; stdlib → third-party → local groups
- `N` (pep8-naming), `UP` (pyupgrade), `B` (bugbear), `SIM` (simplify)
- `# noqa: E402` used deliberately in `main.py` (imports after `load_dotenv()`)
- `# noqa: ARG002` on intentionally-unused interface args (e.g. `_NoCache`)

## Naming

| Kind | Convention | Example |
|------|------------|---------|
| Modules | `snake_case.py` | `whatsapp_helpers.py` |
| Functions | `snake_case`, verb-first | `load_session`, `upsert_customer` |
| Private helpers | leading `_` | `_escape`, `_build`, `_session_token` |
| Tool handlers | `_tool_<action>` | `_tool_add_to_cart` |
| Constants | `UPPER_SNAKE` | `STATUS_LABELS`, `WHATSAPP_MENU_LIMIT`, `_AR_ALIASES` |
| Config singleton | `Config.UPPER_SNAKE` | `Config.SUPABASE_URL` |

## Documentation

- **Module docstrings** describe purpose + public API (see `ai_service.py`, `database.py`)
- **Function docstrings** on most helpers — Google-ish style with `Args:`/`Returns:` in
  `retriever.py`; one-liners elsewhere
- **Section banners** — `# ---- ... ----` comment rules divide files into logical sections
  (consistent across `whatsapp.py`, `ai_service.py`, `database.py`, `whatsapp_helpers.py`)
- Inline comments explain *why*, especially for workarounds (e.g. `_NoCache` Jinja2 fix,
  flat `Msg` model note, catalog-vs-retrieval rationale)

## Configuration Access

- **Single source:** `app/services/config.py::Config` — every env var is a class attribute
- **Never** call `os.getenv()` outside `config.py` (project rule in `CLAUDE.md`)
- `_bool()` helper normalizes truthy strings (`1/true/yes/y`)
- Defaults provided inline (note: some are insecure defaults — see `CONCERNS.md`)

## Database Access Patterns

- **Single adapter:** all SQL goes through `app/db/database.py` (`query`/`execute`/`execute_returning`)
- **`%s` placeholders only** — never f-strings in SQL (SQL-injection rule); params passed as tuple
- `_build()`/`_escape()` substitute params client-side before the Supabase RPC call
- SQL strings are multi-line triple-quoted; `ON CONFLICT ... DO UPDATE` used for upserts
- All SQL is author-written, never from user input; user strings escaped via `_escape()`

## Error Handling

- **Broad try/except for non-critical side effects** — order creation never fails because
  aunt notification failed (`whatsapp.py` confirm branch); knowledge-file loads swallow errors
- **Global exception handler** in `main.py` — `/whatsapp/*` returns friendly JSON @ 200 to
  avoid Meta retry storms; everything else returns generic 500
- **Defensive coercion** — `int(x or 1)`, `float(x or 0)`, `(s or "").strip()` throughout
- **Graceful AI degradation** — `ai_available()` gates Claude; missing key returns a message, not a crash
- `log.warning`/`log.exception` for recoverable failures; module-level loggers

## Async vs Sync

- Mixed: dashboard page routes are `async def`; the WhatsApp `webhook_post` and DB helpers
  are plain `def` (sync) — FastAPI runs sync routes in a threadpool. DB calls are synchronous
  (supabase-py HTTPS), so bot handlers are intentionally sync.

## i18n / RTL

- Customer-facing strings are **Arabic (Palestinian dialect)** by design
- Status keys are English (`to_do`, etc.); Arabic labels live in `STATUS_LABELS`
- Arabic command aliases mapped to English keys via `_AR_ALIASES`
- Unicode normalization (NFKD + diacritic strip) in `retriever._normalize` for matching
- Arabic-Indic numeral rendering in cart display (`digit_map`)

## Frontend (templates)

- Shared premium design system documented in `CLAUDE.md` (green `#006948`, Material Symbols,
  glassmorphism nav, 20px card radius). Keep consistent; do not revert to old `#059669`/DaisyUI.

---

*Conventions analysis: 2026-06-13*
