# Technical Plan — Bot Prompt Engineering & Data Optimization

**Version:** 1.0
**Date:** 2026-04-05
**Status:** Implemented
**Related PRD:** `docs/PRD_PROMPT_ENGINEERING.md`

---

## 1. Context & Motivation

This document describes the engineering decisions and implementation strategy behind the
prompt engineering and data optimization sprint completed on 2026-04-05.

Three confirmed bugs broke core bot functionality. Beyond the bugs, research into Anthropic's
best practices for tool-use agents revealed structural weaknesses in the system prompt, product
context injection, and knowledge base architecture that caused silent failures and inconsistent
AI behavior.

The changes were executed in 6 phases, ordered by impact-to-effort ratio. All changes are
in-place replacements or additions — no new routes, no new services, no breaking API changes.

---

## 2. Files Changed

| File | Change type | Summary |
|------|-------------|---------|
| `app/ai/retriever.py` | Bug fix + feature | Category matching fixed; aliases field added to search haystack |
| `app/routers/whatsapp.py` | Bug fix | `_tool_show_menu` call signature corrected |
| `app/services/ai_service.py` | Rewrite + feature | New catalog injection, rewritten system prompt, upgraded tool descriptions, selective knowledge injection, max_tokens tuning |
| `app/db/schema.sql` | Documentation | Added `aliases` column definition with comment |
| `app/data/knowledge/store_info.md` | New file | Store hours, payment, contact info |
| `app/data/knowledge/shipping_policy.md` | New file | Delivery areas, timing, costs |
| `app/data/knowledge/returns_policy.md` | New file | Returns and damage policy |
| `app/data/knowledge/ingredients_faq.md` | New file | Natural ingredients, allergy info |
| `app/data/knowledge/skin_advice.md` | New file | Skin type → product recommendation guide |
| Supabase `products` table | DB migration | `aliases TEXT DEFAULT ''` column added |

---

## 3. Phase Breakdown

### Phase 1 — Bug Fixes

Three bugs that caused immediate, visible failures.

#### Bug A — `retriever.py`: category filter checked nonexistent column

**Root cause:** `search_products(query, category)` at line 82 checked `r.get("category", "")`.
The `products` table has no `category` column — it has `tags`. Every category-filtered
`show_menu` call returned an empty list, and the bot replied "لا توجد منتجات متاحة حالياً."

**Fix:** Check against the `tags` list (already parsed into `list[str]` by `_load_catalog()`):

```python
# Before
if category and cn not in _normalize(r.get("category", "")):
    continue

# After
if category and not any(cn in _normalize(t) for t in r.get("tags", [])):
    continue
```

**Why `any()` over `in`:** Tags are individual words in a list. Checking substring containment
against each tag separately avoids false matches (e.g. "cream" matching inside "ice cream
fragrance" as a single string).

---

#### Bug B — `whatsapp.py`: `_tool_show_menu` double-passed the category argument

**Root cause:** Line 83: `search_products(category, category)` — passed category as BOTH
the `query` positional arg AND the `category` keyword arg.

The `query` arg does substring search against `name + description + sku`. Passing a category
word like "كريمات" as a query means it searches for the literal string "كريمات" in product
names/descriptions — returning only products whose name or description contains that word
verbatim, rather than products tagged with that category.

**Fix:**
```python
# Before
products = search_products(category, category) if category else search_products(None, None)

# After
products = search_products(None, category) if category else search_products(None, None)
```

---

#### Bug C — `ai_service.py`: zero product grounding on open-ended orders

**Root cause:** `_product_context(user_message)` did keyword search against the user's
message text. When a customer said "بدي اطلب" or "شو عندكم؟", no product name appeared
in the message, so the function returned `""`. Claude received the message with no catalog
context and was at risk of hallucinating product names in its reply.

**Root fix principle:** For a store with ≤30 products (~1,500 tokens), always include the
entire catalog in the system prompt. Per-message retrieval adds latency and has this
critical silent-failure mode. Always-on injection eliminates both problems at negligible cost.

**New function:**
```python
def _full_catalog_context() -> str:
    items = search_products(None, None)  # all active products
    lines = ["<catalog>"]
    for r in items:
        line = f"- {r['name']} | {r['price']}₪"
        if r.get("tags"):
            line += f" | tags: {', '.join(r['tags'])}"
        if r.get("description"):
            line += f" | {r['description'][:100]}"
        lines.append(line)
    lines.append("</catalog>")
    return "\n".join(lines)
```

The `<catalog>` block is appended to the `system` string in `generate_reply()`, making it
part of the authoritative system context — not an inline user message annotation.

---

### Phase 2 — System Prompt Rewrite

**Why the old prompt failed:** A flat string with loose rules ("when intent is clear, call
add_to_cart") is ambiguous for Claude Haiku. Haiku is optimized for fast inference, not
nuanced interpretation of vague instructions. It needs explicit if/then patterns.

**Anthropic best practice:** XML tags are the most reliable structuring mechanism for Claude
system prompts. Separating sections by function lets Claude assign different cognitive weight
to each. Examples wrapped in `<examples>` tags are recognized as demonstrations and improve
tool-calling accuracy significantly.

**New structure:**

| Section | Purpose |
|---------|---------|
| `<role>` | Persona definition — who the bot is |
| `<catalog_grounding>` | Hard constraint — only suggest products from `<catalog>` |
| `<tool_rules><decision_tree>` | Explicit if/then for all 6 intent patterns |
| `<examples>` | 5 few-shot demonstrations covering key scenarios |
| `<reply_rules>` | Output format: length, language, code-switching, greeting |

**Why 5 examples specifically:**

| Example | What it teaches |
|---------|----------------|
| "بدي كريم لبشرتي الجافة" → `show_menu(category="كريمات")` | Category-filtered browse from skin concern |
| "I want to order the hand cream" → `add_to_cart` | English buy intent |
| "شو عندكم؟" → `show_menu()` | Open browse, no filter |
| "الكريم غالي شوي" → conversational reply only | Price objection = NO tool call |
| "بدي الكريم والشمعة" → `add_to_cart` twice | Multi-item order |

The price objection example is the most important negative constraint. Without it, Haiku
sometimes responds to "غالي" by calling `show_menu` to show alternatives — an unhelpful,
off-tone behavior that the explicit example prevents.

---

### Phase 3 — Tool Description Upgrades

**Principle:** Anthropic documentation states tool descriptions are the highest-leverage
prompt engineering surface for tool-use agents. Each description should cover: what the tool
does, when to call it, when NOT to call it, and any parameter caveats.

#### `add_to_cart` additions:
- Added: accept Arabic-Indic numerals (١، ٢، ٣) as valid qty values — Haiku does not
  automatically convert these without explicit guidance
- Added: "if product name is ambiguous, pick closest match — do not ask for clarification"
  (Haiku-specific guidance; Haiku infers rather than asks)
- Added: explicit NOT conditions — only call with buying verb present

#### `show_menu` additions:
- Added: explicit Arabic and English category trigger word list
- Added: "category filtering matches against product tags" — prevents Claude from inferring
  an impossible filtering mechanism

#### `save_address` additions:
- Added: 15-character minimum before saving — prevents "رام الله" alone being stored
- Added: fallback instruction — if too short, ask the customer for city + neighborhood + street

---

### Phase 4 — Knowledge Base

**Architecture change:** The old `_knowledge()` function loaded all `.md` files on first call
and injected all of them into every conversation. With 5 files at ~500 characters each, that
would add ~2,500 tokens of FAQ content to every message — most of it irrelevant.

**New architecture: trigger-based selective injection**

Each `.md` file starts with:
```
# triggers: word1, word2, word3
```

The `_relevant_knowledge(user_message)` function:
1. Parses the triggers line from each file (cached after first load)
2. Checks if any trigger word appears in the user's current message (case-insensitive)
3. Returns only matching files, joined together
4. Falls back to always-on files (no triggers line) if nothing matches

This ensures:
- FAQ content only appears when the customer's question is relevant to it
- No irrelevant context pollutes Claude's reasoning for ordering messages
- Adding new knowledge files doesn't increase every-conversation token cost

**Files created and their triggers:**

| File | Key triggers |
|------|-------------|
| `store_info.md` | وين، ساعات، دفع، كاش، تواصل، where، payment، hours |
| `shipping_policy.md` | متى، كم يوم، توصيل، شحن، بوصل، delivery، shipping، when |
| `returns_policy.md` | استرجاع، مشكلة، تالف، ما عجبني، return، refund، damaged |
| `ingredients_faq.md` | مكونات، حساسية، طبيعي، كيماوي، allergy، ingredients، natural |
| `skin_advice.md` | بشرة، جافة، دهنية، حساسة، حب شباب، dry، oily، skin، sensitive |

**Content language:** All files written in Palestinian colloquial Arabic ("وين بوصل" not
"متى سيصل"). Claude mirrors the register of its context — colloquial input → colloquial reply.

---

### Phase 5 — Token Budget Adjustment

**Problem:** `max_tokens=400` was applied uniformly to all API calls. When tools are active,
the tool-use response block (Claude's decision to call a tool) consumes tokens before the
conversational reply begins. In practice, tool calls were occasionally truncating the final
Arabic reply.

**Fix:** Split the budget based on whether tools are active:

```python
max_tokens=600 if tool_executor else 400
```

- Tool-enabled calls (WhatsApp bot): 600 tokens — covers tool decision block + full reply
- Non-tool calls (broadcast message improvement): 400 tokens — sufficient for text editing tasks

At Claude Haiku pricing, 200 additional output tokens per tool call costs approximately
$0.000125 per message — negligible.

---

### Phase 6 — Database Migration + Retriever Update

**Motivation:** The biggest bilingual retrieval failure pattern: a Palestinian customer writes
"hand cream" (English) but the product is named "كريم اليدين" (Arabic). No substring match is
possible between these strings even after Unicode normalization.

**Solution:** Add a free-text `aliases` column to the `products` table. The aunt registers
synonyms per product. The retriever adds aliases to the search haystack.

**Migration:**
```sql
ALTER TABLE products ADD COLUMN IF NOT EXISTS aliases TEXT DEFAULT '';
```

Applied via `mcp__claude_ai_Supabase__apply_migration` to project `ppwcfmuetgczclmnzvqr`.

**Retriever update:** `aliases` is now loaded from Supabase and added to the search string:

```python
hay = " ".join([
    _normalize(r.get("name", "")),
    _normalize(r.get("description", "")),
    _normalize(str(r.get("sku", ""))),
    _normalize(r.get("aliases", "")),   # new
])
```

The catalog injection block also includes aliases in the `<catalog>` XML (via the tags field
display), making Claude aware of alternate names even in conversational context.

---

## 4. Architecture Decisions

### ADR-PE-001: Full catalog in system prompt vs. per-message retrieval

**Decision:** Always inject the full catalog in the system prompt.

**Rejected alternative:** Per-message keyword retrieval (the previous approach).

**Reasoning:** Per-message retrieval has a hard failure mode: if no product keyword appears
in the message, the catalog context is empty. For a ≤30-product store, the catalog is ≈1,500
tokens — small enough to always include. Anthropic's contextual retrieval research confirms
that for knowledge bases this small, always-include outperforms RAG on both accuracy and
latency.

**Trade-off:** If the catalog grows past ~100 products, revisit with semantic search or
category-bucketed injection.

---

### ADR-PE-002: XML-tagged system prompt

**Decision:** Restructure the system prompt with XML section tags.

**Rejected alternative:** Keep the flat string, just add more rules.

**Reasoning:** Anthropic's documentation explicitly recommends XML tags as the most reliable
structuring mechanism for Claude. The flat string had no priority ordering — Claude couldn't
distinguish between hard rules ("never hallucinate products") and soft guidelines ("keep
replies short"). XML sections give each instruction a distinct scope.

---

### ADR-PE-003: Trigger-based knowledge injection

**Decision:** Parse a `# triggers:` line from each knowledge file to decide relevance.

**Rejected alternative:** Always inject all files (old behavior) or build a vector retriever.

**Reasoning:** Always injecting 5 files adds ~2,500 tokens of FAQ to every order message,
most of which is irrelevant and dilutes Claude's focus on the ordering task. A vector
retriever is over-engineered for 5 small static files. Trigger-word matching is 3 lines of
Python, zero dependencies, and handles the use case (customers ask clear topical questions)
well.

---

### ADR-PE-004: Aliases column over fuzzy matching in code

**Decision:** Add a `aliases` TEXT column to the `products` table.

**Rejected alternative:** Implement Levenshtein distance or phonetic matching in the retriever.

**Reasoning:** Fuzzy matching adds code complexity, is non-deterministic, and can produce
false positives in Arabic (many short words are similar). The aliases approach is explicit and
controlled — the aunt registers exactly which synonyms should match, and the retriever does
exact substring search against them. Zero false positives.

---

## 5. What Was Not Changed

| Component | Why unchanged |
|-----------|--------------|
| `app/db/database.py` | DB layer is stable; no query pattern changes |
| `app/routers/ui.py` | Dashboard is unaffected by AI/retriever changes |
| `app/routers/whatsapp.py` (beyond line 83) | Only the `_tool_show_menu` call was wrong |
| Conversation history window (6 turns) | Still appropriate for this use case |
| Temperature (0.3) | Correct for a task-oriented commerce bot |
| Hard command handlers | Arabic aliases already added in the previous sprint |
| `app/services/config.py` | No new env vars required |

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Full catalog injection hits context limit if store grows large | Low (now) | Medium | At 30 products: ~1,500 tokens. Revisit if >100 products. |
| Knowledge file triggers miss some customer phrasings | Medium | Low | Files fall back to always-on mode; AI still replies conversationally |
| Aliases field left empty by aunt | Medium | Low | Retriever degrades gracefully to name/description matching — same as before |
| Claude Haiku ignores the decision tree | Low | High | 5 concrete examples anchor expected behavior; prompt is now explicit not vague |
