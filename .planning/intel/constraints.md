# Constraints (synthesized intel)

Technical constraints, contracts, and schema extracted from the SPEC-typed docs (`PLAN.md`, `PLAN_PROMPT_ENGINEERING.md`) plus the platform constraints section of `PRD.md`.

---

## Container / runtime architecture
- type: architecture
- source: docs/PLAN.md (§1–2, §7)
- Backend: FastAPI / uvicorn, single process. APScheduler runs in-process (no separate worker).
- Stateful dependencies: Supabase (PostgreSQL, ap-southeast-1) only external state; Meta Cloud API; Anthropic Claude Haiku API.
- Procfile: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. All env vars set in host dashboard.

## Component contracts
- type: api-contract
- source: docs/PLAN.md (§3)
- `database.py` public surface: `query(sql, params)` (SELECT → list[dict]), `execute(sql, params)` (write), `execute_returning(sql, params)` (INSERT…RETURNING → dict). `%s` placeholders only; substituted by `_escape()`/`_build()` before RPC. No psycopg2, no direct TCP.
- `ai_service.py` public surface: `generate_reply(user_message, previous_messages, cart, customer_name, tool_executor)`, `ai_available()`. Tool-agnostic; coupling only via `tool_executor` callback.
- `config.py`: single env-var import point; no other file calls `os.environ`.
- `retriever.py`: returns only `active = true` products; in-memory cache invalidated on any `/products` create/update/toggle/delete.

## HTTP API surface
- type: api-contract
- source: docs/PLAN.md (§4)
- WhatsApp: `GET /whatsapp/webhook` (Meta verify: hub.mode/hub.challenge/hub.verify_token → 200+challenge or 403); `POST /whatsapp/webhook` (`{from_number, text, wa_name}`).
- Dashboard pages (cookie auth): `/login`, `/logout`, `/orders`, `/dashboard`, `/products`, `/broadcast`.
- JSON APIs: `GET /api/orders?status=`, `GET /api/orders/{id}/lines`, `POST /api/orders/{id}/status`, `GET /api/dashboard/stats?month=`, `GET /api/reports/months`, `GET|POST /api/products`, `POST /api/products/{id}`, `POST /api/products/{id}/toggle`, `POST /api/products/{id}/delete`, `GET /api/broadcast/audience?filter=`, `POST /api/broadcast/send`.
- Dev: `POST /dev/test_order` (dev mode only).
- Auth: SHA-256 of `SECRET_KEY:DASHBOARD_PASSWORD` cookie; unauthenticated → redirect `/login`.

## Database schema
- type: schema
- source: docs/PLAN.md (§6); migration in docs/PLAN_PROMPT_ENGINEERING.md (§6)
- Project `ppwcfmuetgczclmnzvqr`, ap-southeast-1. Tables: `products`, `customers` (PK phone), `sessions` (PK phone, cart JSONB, menu_products JSONB), `orders`, `order_lines`, `chat_history`, `follow_ups`, `retry_queue`.
- Order status flow: `to_do → ready → delivered → done`. Each transition WhatsApps the customer; `delivered` creates a `follow_ups` record; `done` generates+sends an invoice.
- Migration (applied): `ALTER TABLE products ADD COLUMN IF NOT EXISTS aliases TEXT DEFAULT '';`

## AI / prompt-engineering constraints
- type: nfr
- source: docs/PLAN_PROMPT_ENGINEERING.md (§5–6)
- Backward compatibility: all changes additive or in-place; no API endpoint changes.
- Performance: full-catalog injection ≤ ~1,500 tokens for a 30-product store; revisit past ~100 products (then semantic / category-bucketed injection).
- Resilience: `_full_catalog_context()` returns `""` silently on catalog-query failure; bot continues without grounding.
- Token budget: `max_tokens=600` (tools) / `400` (no tools); temperature 0.3; 6-turn history.
- Knowledge injection cap: ≤ 20,000 chars total; trigger-based selective injection with always-on fallback.
- Testability: 10 verification scenarios (V-1..V-10) must pass manually via `GET /dev/chat`.

## Platform constraints (external)
- type: nfr
- source: docs/PRD.md (§6)
- Meta WhatsApp: 30 msgs/min per number; templates required for >24h-silent users; webhook must respond < 20s or Meta retries; number must be verified in Meta Business Portal.
- Supabase free tier: 500 MB storage, 2 GB bandwidth/month, unlimited API requests, no direct TCP (HTTPS via supabase-py only).
- Anthropic Claude Haiku: tier-dependent rate limits; `max_tokens=400` baseline (see token-budget variant in conflicts); 6-turn context.
