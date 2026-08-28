# Constraints (synthesized intel)

Technical constraints, contracts, and schema extracted from the SPEC-typed docs (`PLAN.md`, `PLAN_PROMPT_ENGINEERING.md`) plus the platform constraints section of `PRD.md` and production readiness research.

---

## Container / runtime architecture
- type: architecture
- source: docs/PLAN.md (§1–2, §7); .planning/research/ARCHITECTURE.md
- **Current**: Backend FastAPI / uvicorn, single process. APScheduler runs in-process.
- **Proposed (Production)**: Operational split into **Web** (FastAPI) and **Worker** (APScheduler/Durable work) processes.
- Stateful dependencies: Supabase (PostgreSQL, ap-southeast-1); Meta Cloud API; Anthropic Claude Haiku API.
- Procfile: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## Component contracts
- type: api-contract
- source: docs/PLAN.md (§3); .planning/research/ARCHITECTURE.md
- **Current**: `database.py` uses generic `run_query`/`run_exec` RPCs.
- **Proposed (Production)**: Transition to **Typed Table Operations** and **Narrow Transactional RPCs** (e.g., `ingest_webhook_event`, `create_order`). Revoke generic SQL RPCs.
- `ai_service.py`:Coupling only via `tool_executor` callback. Pinned model snapshots for stability.
- `config.py`: Single env-var import point.

## HTTP API surface
- type: api-contract
- source: docs/PLAN.md (§4); .planning/research/ARCHITECTURE.md
- WhatsApp: `POST /whatsapp/webhook` requires **HMAC signature verification (X-Hub-Signature-256)** and support for batched envelopes.
- Dashboard (cookie auth): `/login`, `/logout`, `/orders`, `/dashboard`, `/products`, `/broadcast`. 
- **Proposed (Production)**: Replace password hash cookie with **Supabase Auth + TOTP MFA** and opaque server-side sessions. CSRF protection mandatory.
- Dev: `POST /dev/test_order` (must be disabled in production).

## Database schema
- type: schema
- source: docs/PLAN.md (§6); .planning/research/ARCHITECTURE.md
- Tables: `products`, `customers`, `sessions`, `orders`, `order_lines`, `chat_history`, `follow_ups`, `retry_queue`.
- **Additions required**: `webhook_events` (Inbox), `outbox_jobs` (Outbox), `handoffs`, `order_status_history`, `audit_log`, `worker_heartbeats`.
- Order status flow: `to_do → ready → delivered → done`.
- Migration policy: Use Supabase CLI migrations; no direct dashboard edits.

## AI / prompt-engineering constraints
- type: nfr
- source: docs/PLAN_PROMPT_ENGINEERING.md (§5–6); .planning/research/STACK.md
- Model: **Claude Haiku 4.5 Pinned Snapshot** (e.g., `claude-haiku-4-5-20251001`).
- Context: Full-catalog injection, trigger-based knowledge.
- Safety: Deterministic **Policy Gate** for all model-proposed actions. Model never receives DB/Meta credentials.
- Token budget: 600 (tools) / 400 (no tools) split; temperature 0.3.

## Platform constraints (external)
- type: nfr
- source: docs/PRD.md (§6); .planning/research/STACK.md
- Meta WhatsApp: 30 msgs/min; signature verification; webhook timeout < 20s. **Production requirement**: Durable persistence before response.
- Supabase: **Pro tier required** for production (managed backups, PITR, bandwidth).
- Anthropic Claude Haiku: Rate limits; data retention policy review (12-month requirement).
- Recovery: RPO <= 4 hours, RTO <= 4 hours.
