# Requirements (synthesized intel)

Extracted from the two PRD-typed docs and production readiness research.

Source PRDs:
- `docs/PRD.md` (baseline, 2026-03-27, Status: Active)
- `docs/PRD_PROMPT_ENGINEERING.md` (2026-04-05, Status: Implemented)
- `.planning/research/ARCHITECTURE.md` (Production Requirements)

---

## WhatsApp Bot (source: docs/PRD.md §3.1)

- REQ-bot-webhook — Receive incoming WhatsApp messages via Meta Cloud API webhook (BOT-01).
- REQ-bot-hard-commands — Handle hard commands: `cart`, `clear`, `menu`, `pickup`, `delivery`, `confirm`, `info N` (BOT-02).
- REQ-bot-order-tracking — Handle Arabic order tracking ("وين طلبي" and similar) (BOT-03, BOT-12).
- REQ-bot-number-select — Handle number selection (1/2/3) from last shown menu (BOT-04).
- REQ-bot-quantity-syntax — Handle quantity syntax (`2x1`, `3*2`) (BOT-05).
- REQ-bot-ai-fallback — Fall back to Claude Haiku for unrecognized messages (BOT-06).
- REQ-bot-greeting — Greet new customers on first message (BOT-07).
- REQ-bot-session-persist — Persist cart/stage/address across restarts in Supabase `sessions` (BOT-08).
- REQ-bot-save-address — Save customer address for reuse on future delivery orders (BOT-09).
- REQ-bot-confirm-flow — On `confirm`: write order + lines, send customer confirmation, notify aunt (BOT-10).
- REQ-bot-aunt-notification — Aunt new-order alert includes order#, customer name/phone, items, total, fulfillment, address (BOT-11).
  - acceptance (US-07): fires within seconds on every confirm; never blocks order save if it fails.
- REQ-bot-fulfillment — Support both pickup and delivery (BOT-13).

## AI Conversation (source: docs/PRD.md §3.2)
- REQ-ai-model — Claude Haiku as sole AI model (AI-01).
- REQ-ai-persona — System prompt positions AI as "عمة ALYASMEEN" (AI-02).
- REQ-ai-no-hallucination — Suggest only Supabase-catalog products, no hallucinated products (AI-03).
- REQ-ai-language-mirror — Detect Arabic/English and reply in the same language (AI-04).
- REQ-ai-history-window — History limited to last 6 turns (AI-06, TOK-03).
- REQ-ai-cart-context — Inject cart context into system prompt to guide checkout (AI-07).
- REQ-ai-knowledge-base — Append `app/data/knowledge/*.md` to system prompt (AI-08). [variant — see KB requirements]
- REQ-ai-graceful-degrade — Degrade gracefully if `CLAUDE_API_KEY` unset (AI-10).
- REQ-ai-tools — Provide 4 tools: `add_to_cart`, `show_menu`, `get_order_status`, `save_address` (AI-11).
- REQ-ai-agentic-loop — Tool call → result fed back → final reply, 2 API calls total (AI-12).
- REQ-ai-nl-mutations — NL intents cause real cart/session mutations (AI-13).
- REQ-ai-show-menu-state — `show_menu` sets `session.menu_products` so number selection keeps working (AI-14).
- REQ-ai-tool-executor-callback — Tool execution in `whatsapp.py`; `ai_service.py` tool-agnostic via callback (AI-15).

## Web Dashboard (source: docs/PRD.md §3.3)
- REQ-dash-login — Password login via SHA-256 cookie session (DASH-01).
- REQ-dash-orders-list — Orders list: customer name, inline products, total, status (DASH-02).
- REQ-dash-orders-filter — Filter orders by status (DASH-03).
- REQ-dash-status-update — One-click status update + WhatsApp notify customer (DASH-04, US-08).
- REQ-dash-wa-link — Direct WhatsApp link per customer (DASH-05).
- REQ-dash-stats — Current-month orders count + revenue, prev-month comparison (DASH-06, DASH-07).
- REQ-dash-charts — 30-day daily bar chart + status donut + top-5 products (DASH-08..10).
- REQ-dash-products-crud — Products list/create/edit/toggle/delete (DASH-11..15, US-09).
- REQ-dash-broadcast — Compose + send WhatsApp to a segment; segments all / active-30d / top-10 (DASH-16, DASH-17).
- REQ-dash-pdf-invoice — On status → `done`: generate PDF invoice and send to customer (DASH-18).

## Background Scheduler (source: docs/PRD.md §3.4)
- REQ-sched-followup — Every 6h, follow-up to customers delivered 3+ days ago (SCHED-01).
- REQ-sched-monthly-report — 1st of month 8 AM, Arabic summary to aunt (SCHED-02, US-10).
- REQ-sched-retry-queue — Every 15 min, process retry queue (SCHED-03); max 3 attempts (SCHED-04).

## Non-Functional (source: docs/PRD.md §4)
- REQ-nfr-bilingual — Arabic primary + English, auto-detect per message.
- REQ-nfr-latency — Bot reply < 2s (p95).
- REQ-nfr-uptime — 99% availability.
- REQ-nfr-test-coverage — 85%+ coverage on core bot logic + API endpoints.
- REQ-nfr-security — Dashboard password SHA-256; httponly session cookie; no secrets in code.
- REQ-nfr-data — All customer data in Supabase; no local files.
- REQ-nfr-cost — Optimized for Supabase free tier + Claude Haiku.

---

## Prompt-Engineering Requirements (source: docs/PRD_PROMPT_ENGINEERING.md)

- REQ-ret-tags-match — `search_products(query, category)` matches category against `tags` (RET-01).
- REQ-ret-haystack — Search haystack includes name, description, sku, and new `aliases` (RET-04).
- REQ-cat-full-injection — All active products always injected into system prompt as `<catalog>` XML (CAT-01).
- REQ-prompt-xml — XML sections: `<role>`, `<catalog_grounding>`, `<tool_rules>`, `<examples>`, `<reply_rules>` (PROMPT-01).
- REQ-kb-five-files — Five knowledge files with trigger-based selective injection (KB-01..03).
- REQ-tok-split — `max_tokens=600` when tools enabled, `400` when not (TOK-01).

---

## Production Readiness Requirements (source: .planning/research/ARCHITECTURE.md)

### Reliability and Idempotency
- REQ-prod-inbox — Durable Webhook Inbox persistence before response (M2).
- REQ-prod-outbox — Durable Outbox for messages and side effects (M2).
- REQ-prod-atomic-orders — Atomic transaction for order creation and status transitions (M1).
- REQ-prod-idempotency — Every side effect must have a stable idempotency key (M2).

### Security
- REQ-prod-auth-mfa — Replace shared password with Supabase Auth + TOTP MFA (M4).
- REQ-prod-session-opaque — Use opaque server-side sessions, not client-side signed cookies (M4).
- REQ-prod-csrf — Implement CSRF protection for all mutating dashboard routes (M4).
- REQ-prod-sec-headers — Add CSP, HSTS, and other security headers (M4).
- REQ-prod-raw-hmac — Verify Meta X-Hub-Signature-256 over raw request body (M2).

### AI Governance
- REQ-prod-policy-gate — Deterministic application policy validates all AI-proposed actions (M3).
- REQ-prod-pinned-model — Use pinned model snapshots instead of floating aliases (M2).
- REQ-prod-handoff — Explicit human-handoff state and operator inbox (M3, M4).
- REQ-prod-eval-gate — Pytest-based evaluation release gates for model behavior (M3).

### Observability and Operations
- REQ-prod-struct-log — JSON structured logging with correlation IDs (M2).
- REQ-prod-metrics — Application-level metrics (latency, error rates, cost) and alerts (M2).
- REQ-prod-backup-restore — Automated off-site backups and quarterly restore drills (M1).
- REQ-prod-migrations — Versioned Supabase CLI migrations; no direct dashboard edits (M1).
- REQ-prod-cicd — GitHub Actions for CI/CD with release approvals and rollback (M2).
