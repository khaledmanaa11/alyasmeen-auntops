# Product Requirements Document — Bot Prompt Engineering & Data Optimization

**Version:** 1.0
**Date:** 2026-04-05
**Status:** Implemented
**Scope:** AI layer (`ai_service.py`), product retriever (`retriever.py`), bot logic (`whatsapp.py`), knowledge base (`app/data/knowledge/`), database schema (`products` table)

---

## 1. Problem Statement

The ALYASMEEN WhatsApp bot had three confirmed live defects and several structural weaknesses in how it prompted Claude Haiku and retrieved product data. Together these caused:

- **Broken category menus** — every call to `show_menu(category="كريمات")` returned empty because the retriever checked a `category` column that does not exist in the database.
- **Product hallucination** — when a customer said "بدي اطلب" (I want to order), the per-message product retrieval returned nothing (no product keyword in the message), leaving Claude with zero grounding and a risk of inventing product names or prices.
- **Vague AI decision-making** — the system prompt was a flat, unstructured string with no explicit if/then rules. Claude Haiku, being a smaller model, guessed at the boundary between browsing and buying intent, producing inconsistent behavior.
- **Zero knowledge base content** — the `app/data/knowledge/` directory was empty, meaning the bot had no answers for common customer questions (delivery time, payment method, ingredients, return policy, skin advice).
- **Incomplete product search** — the retriever only searched `name`, `description`, and `sku`. English queries ("hand cream") never matched Arabic product names ("كريم اليدين"), and there was no alias field to bridge the gap.

---

## 2. Goals

| Goal | Metric |
|------|--------|
| Fix category-filtered menu | `show_menu(category="كريمات")` returns products, not empty |
| Eliminate zero-grounding on open-ended orders | Claude always has the full catalog when customer says "بدي اطلب" |
| Reduce tool-call errors | Claude calls the correct tool on first try for the 5 most common intent patterns |
| Add structured decision logic | Bot follows explicit if/then rules, not guesswork |
| Cover top 5 customer FAQ topics | Bot answers: delivery time, payment, ingredients, returns, skin advice |
| Enable bilingual product search | "hand cream" matches "كريم اليدين" via aliases column |

---

## 3. Non-Goals

- Replacing Claude Haiku with a larger model
- Adding new conversation features beyond the existing 4 tools
- Changing the WhatsApp button or order confirmation flow
- Adding product images or multimedia support
- Changing the dashboard UI

---

## 4. Users Affected

### Customer (End User)
- Directly benefits from more accurate menus, better product recommendations, and factual answers to FAQ questions.
- No visible changes to the conversation experience beyond more accurate, faster responses.

### Aunt (Business Owner)
- Can now add an `aliases` field per product to support bilingual matching.
- Knowledge base `.md` files give her a structured way to inform the bot without code changes.
- Tag taxonomy guidance helps her categorize products consistently for correct menu filtering.

---

## 5. Functional Requirements

### 5.1 Product Retrieval

| ID | Requirement |
|----|-------------|
| RET-01 | `search_products(query, category)` must match `category` against the `tags` field (comma-separated text), not a nonexistent `category` column |
| RET-02 | When both `query` and `category` are None, return the first 8 active products |
| RET-03 | When `category` is set, filter products whose `tags` list contains the category keyword (substring match, case-insensitive, diacritic-normalized) |
| RET-04 | The search haystack must include: `name`, `description`, `sku`, and the new `aliases` field |
| RET-05 | The `aliases` field must be loaded from Supabase alongside `name`, `price`, `description`, `tags` |

### 5.2 Catalog Injection (AI Grounding)

| ID | Requirement |
|----|-------------|
| CAT-01 | All active products must always be injected into the Claude system prompt as a `<catalog>` XML block, regardless of what the customer typed |
| CAT-02 | The `<catalog>` block must include: product name, price, tags, and description (truncated to 100 chars) per line |
| CAT-03 | Per-message keyword retrieval (`_product_context`) must be removed — it is replaced by `_full_catalog_context()` |
| CAT-04 | The catalog block is appended to the dynamic `system` string in `generate_reply()`, after the static `_SYSTEM_PROMPT` constant |
| CAT-05 | If the catalog is empty (no active products), the block is omitted silently |

### 5.3 System Prompt Structure

| ID | Requirement |
|----|-------------|
| PROMPT-01 | The system prompt must use XML tags to separate sections: `<role>`, `<catalog_grounding>`, `<tool_rules>`, `<examples>`, `<reply_rules>` |
| PROMPT-02 | The `<tool_rules>` section must contain an explicit `<decision_tree>` with 6 named intent patterns (buy, browse category, open browse, skin concern, product mention only, price objection) |
| PROMPT-03 | The `<examples>` section must contain at least 5 few-shot examples covering: category browse, English add-to-cart, open menu, price objection (no tool), multi-item add |
| PROMPT-04 | The price objection example must explicitly show "no tool call" — this prevents Claude from calling `show_menu` in response to "غالي" |
| PROMPT-05 | The reply rules must specify: max 3 paragraphs, language mirroring, code-switch handling (reply Arabic, keep product names in original language), name-based greeting |

### 5.4 Tool Descriptions

| ID | Requirement |
|----|-------------|
| TOOL-01 | `add_to_cart` description must state: add immediately when buying verb present, do NOT call without buying intent, accept Arabic-Indic numerals (١، ٢، ٣) for qty |
| TOOL-02 | `add_to_cart` description must state: if ambiguous product name, pick closest match — do not ask for clarification |
| TOOL-03 | `show_menu` description must list explicit Arabic and English category trigger words (كريمات، شموع، لوشن، creams، candles، lotions) |
| TOOL-04 | `show_menu` description must state: category filtering works by matching against product tags |
| TOOL-05 | `save_address` description must specify: only call if address is at least city + neighborhood (≥15 characters); if shorter, ask the customer to provide more detail instead |

### 5.5 Knowledge Base

| ID | Requirement |
|----|-------------|
| KB-01 | Five `.md` files must exist in `app/data/knowledge/`: `store_info.md`, `shipping_policy.md`, `returns_policy.md`, `ingredients_faq.md`, `skin_advice.md` |
| KB-02 | Each knowledge file must begin with a `# triggers: word1, word2` comment line listing Arabic and English keywords that indicate when the file is relevant |
| KB-03 | The knowledge loader must parse the triggers line and only inject a file when at least one of its trigger words appears in the customer's current message |
| KB-04 | If no trigger matches, fall back to injecting files that have no triggers line (always-on files) |
| KB-05 | Total injected knowledge content must not exceed 20,000 characters |
| KB-06 | Knowledge files must be written in Palestinian colloquial Arabic, not formal MSA |

### 5.6 Token Budget

| ID | Requirement |
|----|-------------|
| TOK-01 | `max_tokens` must be 600 when tools are enabled (`tool_executor` is passed) and 400 when tools are not used (e.g. broadcast message improvement) |
| TOK-02 | Temperature must remain 0.3 |
| TOK-03 | Conversation history window remains at last 6 turns |

### 5.7 Database

| ID | Requirement |
|----|-------------|
| DB-01 | The `products` table must have an `aliases` column of type `TEXT DEFAULT ''` |
| DB-02 | The `aliases` field stores comma-separated synonyms (e.g. `"hand cream, كريم اليد, كريم للأيدي"`) |
| DB-03 | The schema reference file `app/db/schema.sql` must reflect the new column with a comment explaining its purpose |

---

## 6. Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Backward compatibility | All changes are additive or replacement-in-place; no existing API endpoints change |
| Performance | Full catalog injection adds ≤1,500 tokens per request for a 30-product store — within Haiku's context window |
| Resilience | If the catalog query fails, `_full_catalog_context()` returns `""` silently — the bot continues without product grounding |
| Maintainability | Knowledge files are plain Markdown — the aunt or Khaled can edit them without touching Python code |
| Testability | All 10 `docs/TODO_PROMPT_ENGINEERING.md` verification scenarios (V-1 through V-10) must pass manually via `/dev/chat` |

---

## 7. Product Data Standards (Aunt's Responsibility)

These are not code requirements — they are data-entry standards for the `/products` dashboard.

### 7.1 Description Format

Each product description should follow this template:
```
مثالي لـ [نوع البشرة أو المشكلة].
[الفائدة الرئيسية — جملة واحدة].
مكوناته الطبيعية: [2–3 مكونات رئيسية].
يُستخدم [صباحًا / مساءً / يوميًا].
```

Opening with the skin problem ensures the retriever can match customer queries like "بشرة جافة" even if the product name contains no such words.

### 7.2 Tag Taxonomy

All products must use tags from the following taxonomy. Use underscores, not spaces (they survive Unicode normalization in the retriever).

```
# Category (choose one):
كريمات | لوشن | شموع | عناية_جسم | عناية_وجه | عناية_يدين

# Skin concern (choose all that apply):
بشرة_جافة | بشرة_دهنية | بشرة_حساسة | مضاد_شيخوخة | ترطيب | تفتيح

# Occasion (optional):
هدية | يومي | ليلي | صباحي
```

Maximum 6 tags per product.

### 7.3 Aliases Field

The `aliases` column (new) accepts comma-separated alternative names.

Examples:
- A product named "كريم اليدين" → aliases: `hand cream, كريم اليد, كريم للأيدي`
- A product named "شمعة اللافندر" → aliases: `lavender candle, شمعة لافندر`

Aliases enable English-speaking customers to find Arabic-named products and vice versa.

---

## 8. Acceptance Criteria

The following scenarios must pass when tested manually via `GET /dev/chat`:

| # | Scenario | Expected Outcome |
|---|----------|-----------------|
| 1 | Customer sends "بدي كريمات" | Bot calls `show_menu(category="كريمات")` and returns a filtered product list — not "no products available" |
| 2 | Customer sends "بدي اطلب" | Bot calls `show_menu()` with no filter and returns the full product list — Claude does not guess product names |
| 3 | Customer sends "الكريم غالي شوي" | Bot replies conversationally about product quality — does NOT call `show_menu` or `add_to_cart` |
| 4 | Customer sends "بدي الكريم والشمعة" | Bot calls `add_to_cart` twice and confirms both were added |
| 5 | Customer sends "شو المكونات؟" | Bot answers using content from `ingredients_faq.md` |
| 6 | Customer sends "I want hand cream" (after product has alias `hand cream`) | Bot finds the product and adds it to cart |
| 7 | Customer sends "وين بوصل طلبي؟" | Bot injects `shipping_policy.md` content and answers delivery timing |

---

## 9. Out of Scope (Future Phases)

| Item | Reason deferred |
|------|----------------|
| Fuzzy matching in retriever (Levenshtein distance) | Aliases column covers 90% of bilingual mismatch cases with zero complexity cost |
| Vector/semantic product search | Overkill for a 30-product catalog; revisit if catalog grows past 100 products |
| Multi-turn skincare consultation flow | Requires conversation state tracking beyond current stage field |
| Automated tag suggestion | Not needed while catalog is managed manually by one person |
| A/B testing of prompt variants | Out of scope for a solo-owner business at this volume |
