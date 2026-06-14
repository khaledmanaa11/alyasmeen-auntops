# Context Notes (synthesized intel)

Running notes from DOC-typed sources, appended with provenance. These are background/log material — lower precedence than SPEC/PRD. Where a DOC describes a superseded design, that is flagged in `INGEST-CONFLICTS.md` (auto-resolved INFO).

---

## Topic: Production system prompt & prompt-design principles
- source: docs/PROMPTS.md

- `_SYSTEM_PROMPT` is a fixed Arabic string positioning the bot as "عمة ALYASMEEN": suggest only catalog products (no invented names/prices), recommend 1–3 products when intent is clear, ask 1–2 clarifying questions max, keep replies ≤3 paragraphs / 6 bullets, mirror customer language, include a medical-disclaimer line. (Full AR text + English translation in source.)
- Runtime additions to the system prompt: customer-name greeting line; knowledge-base content ("معلومات عن المتجر"); cart context (items, total, "confirm" nudge).
- Tool table (4 tools) and the 2-call agentic loop documented (matches ADR-005).
- Tool descriptions written in English regardless of UI language (more reliable tool selection); `add_to_cart.product_name` is free-form (substring-matched), not an ID.
- temperature=0.3 for factual reliability.
- NOTE (superseded design — see conflicts): PROMPTS.md Principle 1 states catalog context is injected **inline in the user message, not the system prompt**, and Principle 4 states **`max_tokens=400` for all calls**. Both are superseded by PLAN_PROMPT_ENGINEERING.md (SPEC) / PRD_PROMPT_ENGINEERING.md — full catalog now goes in the system prompt and `max_tokens` is 600/400 split.

## Topic: Development prompt history (Claude Code build log)
- source: docs/PROMPTS.md (Development Prompts section)
- Iterative build prompts captured: initial setup (Supabase + FastAPI + Jinja2 + Haiku, removing Odoo/AppSheet); AI-service consolidation into single `ai_service.py`; orders-page redesign; aunt notification system; products dashboard page + cache invalidation; broadcast messaging; agentic tool-use upgrade. Each entry records the prompt and the resulting outcome.

## Topic: Deployment & post-launch checklist (original)
- source: docs/TODO.md (2026-03-27)
- Deployment: push to GitHub, create Railway/Render service, set env vars (SUPABASE_URL, SUPABASE_KEY, DASHBOARD_PASSWORD, SECRET_KEY, AUNT_PHONE, CLAUDE_API_KEY), `USE_MOCK_WHATSAPP=0`, verify start, confirm dashboard.
- Real products: add via `/products` (catalog.json legacy/unused); products visible to bot instantly; toggle/delete placeholders.
- WhatsApp config: set WA_META_TOKEN / WA_META_PHONE_ID / WA_META_VERIFY_TOKEN / (optional) WA_META_APP_SECRET; register webhook `https://<app>/whatsapp/webhook` subscribing to `messages`; test locally via ngrok.
- Completed log lists: 14 original improvement steps, AppSheet removal, Supabase HTTPS, orders redesign, aunt notification, schedulers (follow-up/monthly/retry), **Wave invoicing wired (status → done)**, **PDF invoice on completion**, products dashboard, products→Supabase, broadcast, end-to-end local testing.
- NOTE (superseded KB guidance — see conflicts): TODO.md Knowledge Base section suggests files `store_info.md`, `faq.md`, `return_policy.md`, `ingredients.md` loaded once at startup and **all appended** to the prompt. Superseded by PRD/PLAN_PROMPT_ENGINEERING.md — five specific files (store_info, shipping_policy, returns_policy, ingredients_faq, skin_advice) with trigger-based selective injection.
- NOTE (invoice mechanism — see conflicts): TODO.md lists both Wave invoicing and PDF invoice as done; SPEC/PRD document only PDF invoicing on `done`.

## Topic: Prompt-engineering sprint status & verification backlog
- source: docs/TODO_PROMPT_ENGINEERING.md (2026-04-05)
- Code complete: all 3 bug fixes (A retriever category→tags, B whatsapp `_tool_show_menu` arg, C ai_service full-catalog injection), XML system-prompt rewrite, tool-description upgrades, 5 knowledge files + `_relevant_knowledge()`, max_tokens 600/400 split, aliases migration + retriever update, schema doc.
- Audit fixes (2026-04-05): CAT-01 critical — `_full_catalog_context()` was capped at 8 via `search_products(None,None)`, now calls `_catalog()` for ALL active products; KB-04 — added `about_store.md` as a no-triggers always-on file (the always-on fallback was dead because all 5 files had triggers); KB-06 — `skin_advice.md` reworded from "search the catalog" to "recommend products"; doc fix — verification count corrected 5→10, retriever docstring 8/12 split.
- Verification backlog (manual via `/dev/chat`): V-1..V-10 (category menu, open-order intent, price objection no-tool, multi-item, ingredients FAQ, bilingual alias match, delivery question, short-address rejection, English add-to-cart, mention-without-buying-intent). All currently unchecked.
- Pending data tasks (aunt/Khaled, no code): rewrite descriptions problem-first; standardize tags to taxonomy; fill aliases; fill real knowledge-file content (currently placeholders).
- Deferred (not scheduled): fuzzy matching, semantic/vector search, multi-turn consultation flow, prompt A/B testing, auto-tag suggestions.
