# Requirements (synthesized intel)

Extracted from the two PRD-typed docs. Where the two PRDs diverge on the same scope, **both variants are preserved** and flagged in `INGEST-CONFLICTS.md` (competing-variants). Synthesis does NOT pick a winner.

Source PRDs:
- `docs/PRD.md` (baseline, 2026-03-27, Status: Active)
- `docs/PRD_PROMPT_ENGINEERING.md` (2026-04-05, Status: Implemented)

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

## AI Conversation (source: docs/PRD.md §3.2) — see competing variants below
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
- REQ-dash-pdf-invoice — On status → `done`: generate PDF invoice and send to customer (DASH-18). [see invoice discrepancy in conflicts]

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

### Product Retrieval (§5.1)
- REQ-ret-tags-match — `search_products(query, category)` matches category against `tags` (comma-text), not a `category` column (RET-01).
- REQ-ret-default-8 — When query+category both None, return first 8 active products (RET-02).
- REQ-ret-category-filter — Category filter = substring match on tags, case-insensitive, diacritic-normalized (RET-03).
- REQ-ret-haystack — Search haystack includes name, description, sku, and new `aliases` (RET-04).
- REQ-ret-load-aliases — Load `aliases` from Supabase alongside name/price/description/tags (RET-05).

### Catalog Injection (§5.2) — COMPETING with REQ-ai-* AI-05 (see conflicts)
- REQ-cat-full-injection — All active products always injected into system prompt as `<catalog>` XML, regardless of message (CAT-01).
- REQ-cat-line-format — `<catalog>` line includes name, price, tags, description≤100 chars (CAT-02).
- REQ-cat-remove-per-message — Remove per-message `_product_context`; replace with `_full_catalog_context()` (CAT-03).
- REQ-cat-append-system — Catalog appended to dynamic `system` string after static `_SYSTEM_PROMPT` (CAT-04).
- REQ-cat-empty-omit — Omit block silently if no active products (CAT-05).

### System Prompt Structure (§5.3)
- REQ-prompt-xml — XML sections: `<role>`, `<catalog_grounding>`, `<tool_rules>`, `<examples>`, `<reply_rules>` (PROMPT-01).
- REQ-prompt-decision-tree — `<tool_rules>` contains `<decision_tree>` with 6 named intent patterns (PROMPT-02).
- REQ-prompt-examples — ≥5 few-shot examples (category browse, English add, open menu, price objection no-tool, multi-item) (PROMPT-03).
- REQ-prompt-price-objection — Price-objection example explicitly shows "no tool call" (PROMPT-04).
- REQ-prompt-reply-rules — Max 3 paragraphs, language mirroring, code-switch handling, name greeting (PROMPT-05).

### Tool Descriptions (§5.4)
- REQ-tool-add-cart-desc — `add_to_cart`: add on buying verb, never without buying intent, accept Arabic-Indic numerals; pick closest match when ambiguous (TOOL-01, TOOL-02).
- REQ-tool-show-menu-desc — `show_menu`: explicit AR/EN category triggers; filter via tags (TOOL-03, TOOL-04).
- REQ-tool-save-address-desc — `save_address`: only call if ≥15 chars (city+neighborhood); else ask for more detail (TOOL-05).

### Knowledge Base (§5.5) — variant of REQ-ai-knowledge-base / supersedes TODO.md KB
- REQ-kb-five-files — Five files exist: store_info, shipping_policy, returns_policy, ingredients_faq, skin_advice (KB-01).
- REQ-kb-triggers-line — Each file begins with `# triggers: word1, word2` (AR+EN keywords) (KB-02).
- REQ-kb-selective-inject — Loader injects a file only when a trigger appears in the current message (KB-03).
- REQ-kb-always-on-fallback — Fall back to no-triggers (always-on) files when nothing matches (KB-04). [audit: added `about_store.md`]
- REQ-kb-char-cap — Total injected knowledge ≤ 20,000 chars (KB-05).
- REQ-kb-colloquial — Files written in Palestinian colloquial Arabic, not MSA (KB-06).

### Token Budget (§5.6) — COMPETING with REQ-ai-* AI-09 (see conflicts)
- REQ-tok-split — `max_tokens=600` when tools enabled, `400` when not (TOK-01).
- REQ-tok-temperature — Temperature stays 0.3 (TOK-02).
- REQ-tok-history — History window stays 6 turns (TOK-03).

### Database (§5.7)
- REQ-db-aliases-column — `products.aliases` column `TEXT DEFAULT ''` (DB-01).
- REQ-db-aliases-format — `aliases` stores comma-separated synonyms (DB-02).
- REQ-db-schema-doc — `app/db/schema.sql` reflects the new column with a comment (DB-03).

### Acceptance scenarios (§8) — manual via GET /dev/chat
1. "بدي كريمات" → `show_menu(category="كريمات")`, filtered list (not empty).
2. "بدي اطلب" → `show_menu()` no filter, full list, no guessed names.
3. "الكريم غالي شوي" → conversational reply, NO tool call.
4. "بدي الكريم والشمعة" → `add_to_cart` twice.
5. "شو المكونات؟" → answer from ingredients_faq.md.
6. "I want hand cream" (alias set) → product found + added.
7. "وين بوصل طلبي؟" → shipping_policy.md content + delivery timing.

### Data-entry standards (§7, aunt's responsibility — not code reqs)
- Description template: problem-first → benefit → ingredients → usage timing.
- Tag taxonomy (underscores, max 6): category (كريمات|لوشن|شموع|عناية_جسم|عناية_وجه|عناية_يدين), skin concern, occasion.
- Aliases: comma-separated AR+EN synonyms per product.
