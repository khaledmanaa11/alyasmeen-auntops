# TODO — Bot Prompt Engineering & Data Optimization

**Date:** 2026-04-05
**Last audit:** 2026-04-05 — 4 issues found and resolved (see Audit Fixes below)
**Status:** Code complete. Awaiting real product data and manual verification.

---

## Code — Completed ✅

- [x] **Bug A:** Fix `retriever.py` — category filter now matches against `tags` list, not nonexistent `category` column
- [x] **Bug B:** Fix `whatsapp.py` — `_tool_show_menu` call changed from `search_products(category, category)` to `search_products(None, category)`
- [x] **Bug C:** Fix `ai_service.py` — full catalog always injected in system prompt as `<catalog>` block; per-message `_product_context()` removed
- [x] **Prompt:** Rewrite `_SYSTEM_PROMPT` with XML structure — `<role>`, `<catalog_grounding>`, `<tool_rules>` + decision tree, `<examples>` (5), `<reply_rules>`
- [x] **Tools:** Upgrade `add_to_cart` description — Arabic-Indic numerals, no-confirm rule, ambiguity guidance
- [x] **Tools:** Upgrade `show_menu` description — explicit Arabic/English trigger words, tags-based filtering note
- [x] **Tools:** Upgrade `save_address` description — 15-character minimum guard, ask for more detail if too short
- [x] **Knowledge:** Create `app/data/knowledge/store_info.md`
- [x] **Knowledge:** Create `app/data/knowledge/shipping_policy.md`
- [x] **Knowledge:** Create `app/data/knowledge/returns_policy.md`
- [x] **Knowledge:** Create `app/data/knowledge/ingredients_faq.md`
- [x] **Knowledge:** Create `app/data/knowledge/skin_advice.md`
- [x] **Knowledge:** Replace `_knowledge()` with `_relevant_knowledge(user_message)` — trigger-keyword selective injection
- [x] **Tokens:** `max_tokens=600` for tool-enabled calls, `400` for non-tool calls
- [x] **DB:** Run migration — `ALTER TABLE products ADD COLUMN IF NOT EXISTS aliases TEXT DEFAULT ''`
- [x] **Retriever:** Load `aliases` from Supabase in `_load_catalog()`
- [x] **Retriever:** Add `aliases` to search haystack in `search_products()`
- [x] **Schema:** Update `app/db/schema.sql` to document the `aliases` column

---

## Audit Fixes — Applied 2026-04-05 ✅

Found during critical PRD compliance audit. All 4 issues were fixed immediately.

- [x] **CAT-01 FIX (critical):** `_full_catalog_context()` was calling `search_products(None, None)` which returns at most 8 products. Now calls `_catalog()` directly — returns ALL active products regardless of count. PRD requires "all active products always injected."
- [x] **KB-04 FIX (dead code path):** All 5 knowledge files had trigger lines, so the "always-on" fallback (`unfiltered`) was always empty. Added `about_store.md` (no triggers line) as a minimal always-on file. Now every conversation gets basic store identity context even when no trigger keywords match.
- [x] **KB-06 FIX (misleading instruction):** `skin_advice.md` told Claude to "ابحثي في الكتالوج" (search the catalog) — Claude reads context, it doesn't search. Rewritten to use "أوصي بالمنتجات..." phrasing instead.
- [x] **Doc fix:** PRD NFR said "All 5 verification scenarios" — corrected to 10. Retriever docstring said "up to 12" for no-filter case — corrected to show 8/12 split.

---

## Verification — Manual Testing Required 🔲

Test all scenarios via `GET /dev/chat` (the WhatsApp simulator at `/dev/chat`).

- [ ] **V-1 — Category menu:** Send "بدي كريمات"
  → Expected: bot calls `show_menu(category="كريمات")` and returns a filtered product list
  → Fail condition: "لا توجد منتجات متاحة حالياً" or a full unfiltered menu

- [ ] **V-2 — Open order intent:** Send "بدي اطلب"
  → Expected: bot calls `show_menu()` with no filter and returns the full product list
  → Fail condition: bot guesses a product name or says it doesn't understand

- [ ] **V-3 — Price objection:** Send "الكريم غالي شوي"
  → Expected: conversational reply about natural quality — NO tool call
  → Fail condition: bot calls `show_menu` or `add_to_cart`

- [ ] **V-4 — Multi-item order:** Send "بدي الكريم والشمعة"
  → Expected: both products added to cart (two `add_to_cart` calls)
  → Fail condition: only one product added, or bot asks "which one?"

- [ ] **V-5 — Ingredients question:** Send "شو المكونات؟"
  → Expected: bot answers using `ingredients_faq.md` content (mentions olive oil, coconut oil, etc.)
  → Fail condition: bot says it doesn't know or gives a generic reply

- [ ] **V-6 — Bilingual alias match:** Add `aliases = "hand cream"` to a product in `/products` dashboard, then send "I want to order hand cream"
  → Expected: product found and added to cart
  → Fail condition: "لم أجد منتجاً" error

- [ ] **V-7 — Delivery question:** Send "متى بوصل طلبي؟" (before ordering)
  → Expected: bot answers from `shipping_policy.md` content (delivery timing)
  → Fail condition: bot says it doesn't know delivery time

- [ ] **V-8 — Short address rejected:** In a delivery flow, send "رام الله" as the address
  → Expected: bot asks for city + neighborhood + street; does NOT call `save_address`
  → Fail condition: "رام الله" saved as full delivery address

- [ ] **V-9 — English add-to-cart:** Send "I want to buy the [product name in English]"
  → Expected: bot calls `add_to_cart` immediately without asking follow-up questions
  → Fail condition: bot asks "are you sure?" or calls `show_menu` first

- [ ] **V-10 — Product mention without buying intent:** Send "الكريم الفلاني" with no buying verb
  → Expected: bot asks "بدك تضيفه للسلة؟" — does NOT add to cart automatically
  → Fail condition: product added to cart without confirmation

---

## Product Data — Aunt's Task 🔲

These are data-entry tasks to be done by the aunt or Khaled via the `/products` dashboard.
**No code changes needed.**

- [ ] For every product: rewrite description to start with the problem it solves
  - Template: "مثالي لـ [نوع البشرة / المشكلة]. [الفائدة الرئيسية]. مكوناته: [2–3 مكونات]. يُستخدم [صباحًا/مساءً/يوميًا]."

- [ ] For every product: standardize `tags` to the approved taxonomy (underscores, no spaces):
  - Category: `كريمات` | `لوشن` | `شموع` | `عناية_جسم` | `عناية_وجه` | `عناية_يدين`
  - Skin concern: `بشرة_جافة` | `بشرة_دهنية` | `بشرة_حساسة` | `مضاد_شيخوخة` | `ترطيب` | `تفتيح`
  - Occasion: `هدية` | `يومي` | `ليلي` | `صباحي`
  - Max 6 tags per product

- [ ] For every product: fill in the `aliases` field with English and Arabic synonym names
  - Example: product "كريم اليدين" → aliases: `hand cream, كريم اليد, كريم للأيدي`
  - This enables bilingual matching (English customers can find Arabic-named products)

---

## Knowledge Base — Fill In Real Info 🔲

The knowledge files exist but contain placeholder values that need real data from the aunt.

- [ ] **`store_info.md`:** Add real working hours, contact number, pickup location/instructions
- [ ] **`shipping_policy.md`:** Add real delivery fee amounts, actual delivery areas served
- [ ] **`returns_policy.md`:** Confirm return/exchange policy with aunt and update text
- [ ] **`ingredients_faq.md`:** Add any product-specific ingredient details or allergen info
- [ ] **`skin_advice.md`:** Fill in specific product names under each skin type (dry, oily, sensitive)
  - These are currently placeholders: "[اسم المنتج المناسب — تُعبأ لاحقًا]"

---

## Future Improvements (Not Scheduled) 🔲

These are identified but deliberately deferred. Do not start until the above is verified.

- [ ] **Fuzzy matching** in retriever — allow 1-character typo tolerance for Arabic product names
  - Defer until the aliases column proves insufficient in practice

- [ ] **Semantic/vector product search** — embed product descriptions and use cosine similarity
  - Overkill for ≤30 products; revisit if catalog grows past 100 products

- [ ] **Skincare consultation flow** — multi-turn guided recommendation (ask 3 questions, suggest 1 product)
  - Requires conversation state machine beyond the current `stage` field

- [ ] **Prompt A/B testing** — log which prompt variant produced an order vs. a drop-off
  - Needs analytics infrastructure not yet in place

- [ ] **Auto-tag suggestions** — when adding a product, suggest tags based on description keywords
  - Nice-to-have for the `/products` dashboard UX
