# Prompt Engineering Log — ALYASMEEN AuntOps

**Project:** ALYASMEEN AuntOps
**AI Model:** Claude Haiku (`claude-haiku-4-5-20251001`)
**Single AI file:** `app/services/ai_service.py`

---

## System Prompts in Production

### WhatsApp Bot System Prompt (`ai_service.py`)

**Purpose:** Guides Claude Haiku to behave as "عمة ALYASMEEN" — a friendly and knowledgeable Arabic skincare advisor who recommends only real products from the catalog and keeps replies short for WhatsApp.

**Current prompt (from `_SYSTEM_PROMPT` in `ai_service.py`):**

```
أنتِ 'عمة ALYASMEEN' — مساعدة ودودة ومتخصصة في منتجات العناية الطبيعية
والمصنوعة يدويًا (كريمات، لوشن، شموع) من فلسطين.

القواعد:
- اقترحي فقط منتجات موجودة في الكتالوج المرفق. لا تخترعي أسماء أو أسعارًا.
- إذا كان طلب الزبون واضحًا (نوع البشرة + المشكلة)، ابدئي بتوصية 1–3 منتجات مباشرة.
- اسألي 1–2 سؤال توضيحي فقط عند الضرورة.
- لكل منتج: الاسم + الفائدة الرئيسية + السعر (إن وُجد) + سطر قصير للاستخدام.
- ردودك قصيرة ومباشرة (3 فقرات كحد أقصى أو 6 نقاط).
- هذا ليس بديلاً عن استشارة طبيب.
- إذا كتب المستخدم بالإنجليزية، ردّي بالإنجليزية. وإلا فبالعربية.
```

**Translation (for reference):**

```
You are 'Aunt ALYASMEEN' — a friendly assistant specializing in natural and
handmade skincare products (creams, lotions, candles) from Palestine.

Rules:
- Suggest only products present in the attached catalog. Do not invent names or prices.
- If the customer's request is clear (skin type + problem), start with 1–3 product
  recommendations directly.
- Ask 1–2 clarifying questions only when necessary.
- For each product: name + main benefit + price (if available) + short usage note.
- Keep replies short and direct (max 3 paragraphs or 6 bullet points).
- This is not a substitute for medical advice.
- If the user writes in English, reply in English. Otherwise, reply in Arabic.
```

**Design decisions:**

1. **Arabic-first persona:** The aunt character is defined in Arabic. This anchors the AI in the right cultural and linguistic register even when a customer switches to English.

2. **No hallucination rule:** The single most important rule is "suggest only products from the catalog." Without this, Claude will confidently invent product names and prices that don't exist. Injecting real catalog context per-request reinforces this.

3. **Short responses:** WhatsApp is a messaging app, not a web page. Long responses get ignored or feel overwhelming. The 3-paragraph / 6-bullet limit matches user behavior on WhatsApp. This is also enforced by `max_tokens=400`.

4. **Language detection built into the prompt:** Rather than detecting language in Python and switching prompts, we put the rule in the prompt itself. Claude follows this reliably — Arabic input gets Arabic output, English input gets English output.

5. **1–2 clarifying questions maximum:** Without this constraint, Claude tends to ask multiple questions before making any recommendation. The rule pushes it toward a recommendation-first approach.

**Dynamic additions to the system prompt (at runtime):**

The base prompt is extended in `generate_reply()` depending on context:

- **Customer name:** `"اسم الزبون/ة: {name}. خاطبيه/ا باسمه/ا عند الترحيب أو التوصية."`
  Added when the customer's name is known, so Claude can address them personally.

- **Knowledge base:** Content of all `.md` files in `app/data/knowledge/` is appended as `"معلومات عن المتجر (للقراءة فقط):\n{content}"`. Loaded once at startup.

- **Cart context:** Current cart items and total are appended so Claude can reference what the customer has selected and nudge them toward `confirm`. Format:
  ```
  سلة الزبون الحالية:
  - كريم اليدين × 2 = 50.00₪
  الإجمالي: 50.00₪
  (إذا أراد الزبون التأكيد، ذكّره بكتابة 'confirm')
  ```

---

## Prompt Design Principles

### 1. Catalog context in the user message, not the system prompt

Product context is injected inline at the end of the user's message (separated by `---`), not in the system prompt. This is intentional.

**Reason:** The system prompt is cached and reused across requests. If products were injected there, they would reflect the state at startup, not the current catalog. By injecting catalog context in the user message, the product list is always fresh — whatever is currently active in Supabase.

**Implementation in `_build_messages()`:**
```python
ctx = _product_context(user_message)
full_user_content = user_message
if ctx:
    full_user_content += f"\n\n---\n{ctx}"
messages.append({"role": "user", "content": full_user_content})
```

### 2. History limited to last 6 turns

`previous_messages[-6:]` is passed to Claude. This is a deliberate cost and quality trade-off.

**Reason:** Full conversation history can become very long (especially for chatty customers). Longer context = higher token cost per request. In practice, the last 6 turns (3 exchanges) contain the relevant context for the current question. Earlier turns are usually about browsing, not the active decision.

**Implementation:** History is stored in the Supabase `chat_history` table and loaded on every AI request.

### 3. Cart context injected at reply time

The current cart is passed to `generate_reply()` from the WhatsApp router and appended to the system prompt. This lets Claude reference items the customer has selected without those items being part of the conversation history.

**Reason:** The cart changes frequently (items added, quantities updated). Tracking it in conversation history would create inconsistency. Injecting it fresh per request is simpler and more accurate.

### 4. max_tokens=400 for WhatsApp format

All Claude calls use `max_tokens=400`. This is lower than the Haiku default.

**Reason:**
- WhatsApp messages that are too long are scrolled past without reading
- Shorter responses feel more conversational and less like a FAQ page
- Limits cost per message — at 10–30 orders per day with multiple messages per order, this adds up
- The system prompt's "3 paragraphs max" rule handles the qualitative limit; max_tokens handles the hard cap

### 5. Tool use: Claude as an agent, not just a responder

The bot now passes 4 tool definitions to Claude on every AI call. Claude can choose to call them instead of (or before) writing a reply.

**Tools defined in `_TOOLS` (`ai_service.py`):**

| Tool | When Claude uses it | What it actually does |
|------|--------------------|-----------------------|
| `add_to_cart(product_name, qty)` | Customer clearly says they want to buy/add something | Searches Supabase catalog by name, appends item to session cart |
| `show_menu(category?)` | Customer asks to browse or see products | Loads active products from Supabase, sets `session.menu_products` so number selection still works |
| `get_order_status()` | Customer asks about their order / delivery | Queries `orders` table, returns real status string |
| `save_address(address)` | Customer provides a delivery address mid-conversation | Writes to `customers.saved_address` + session |

**Agentic loop flow:**
```
1. Client call 1 → Claude picks tool (stop_reason="tool_use")
2. tool_executor(name, input) runs in whatsapp.py → returns result string
3. Result appended as tool_result message
4. Client call 2 → Claude writes final reply knowing the result
```

**Design decisions:**
- Tool descriptions are written in English regardless of UI language, because Anthropic models respond to tool descriptions in the language they're written — English descriptions produce more reliable tool selection than Arabic ones.
- `product_name` in `add_to_cart` is intentionally free-form (not an ID) — the tool handler uses `search_products()` with substring matching, so Arabic spelling variations still match.
- `show_menu` sets `st["menu_products"]` so the existing number-selection hard command (`"1"`, `"2"`, `"3"`) keeps working after an AI-triggered menu — the two paths are compatible.
- If Claude calls a tool but the product isn't found, the tool returns an Arabic error string that Claude incorporates naturally into its reply.

### 5. temperature=0.3 for factual reliability

`temperature=0.3` is used (lower than default).

**Reason:** Product recommendations need to be accurate and consistent. Higher temperature introduces creative variation that can lead to invented product details. Lower temperature keeps Claude on-catalog and predictable.

---

## Development Prompts Used with Claude Code

The following describes the iterative prompts used during development of this project.

### Initial project setup

> "I have a Python project called ALYASMEEN AuntOps — a WhatsApp ordering bot for a Palestinian skincare business. It currently uses Odoo and AppSheet which are both being removed. I need to replace them with: Supabase (PostgreSQL via HTTPS using supabase-py, no psycopg2), a custom FastAPI web dashboard with Jinja2 templates, and Claude Haiku for AI conversation. The bot handles Arabic and English. Please help me build this step by step."

**Outcome:** Established the core architecture, database schema, and initial routing structure.

### AI service consolidation

> "The project has three AI files: ai_aunt.py, ai/assistant.py, and ai/claude_client.py. Consolidate them into a single ai_service.py. It should: use Claude Haiku only, build the system prompt in Arabic, inject product context inline in the user message (not system prompt), limit history to 6 turns, and support cart context injection."

**Outcome:** Created `app/services/ai_service.py` as the single AI file with all prompt engineering.

### Dashboard redesign

> "The orders page is too sparse. Redesign it so: the customer's name is the main headline, products are listed inline in the order card (not behind a click), there's a direct WhatsApp link to message the customer, the action button reflects the next status (not a dropdown), and the page auto-refreshes every 30 seconds."

**Outcome:** Redesigned `orders.html` and the `/api/orders` endpoint to join customers and order_lines.

### Aunt notification system

> "When a customer types 'confirm' and the order is created, immediately send a WhatsApp notification to AUNT_PHONE. The message should include the order number, customer name and phone, list of items with quantities, total, fulfillment type (delivery or pickup), and address if delivery. Wrap the whole thing in try/except — the order must never fail because of a notification error."

**Outcome:** Added the aunt notification block at the end of the `confirm` handler in `whatsapp.py`.

### Product management page

> "Add a /products page to the dashboard where the aunt can add, edit, toggle active/inactive, and delete products. Products should be stored in the Supabase 'products' table, not catalog.json. The bot should pick up changes instantly — add a cache invalidation call to retriever.py whenever the products API is modified."

**Outcome:** Created the products dashboard page, products API endpoints, and updated `retriever.py` to use Supabase with an invalidatable cache.

### Broadcast messaging

> "Add a /broadcast page to the dashboard. The aunt should be able to type a custom WhatsApp message and send it to one of three audiences: all customers, customers who ordered in the last 30 days, or the top 10 customers by order count. Show a preview of how many customers will receive the message before sending."

**Outcome:** Added the broadcast page, audience API, and send endpoint to `ui.py`.

### Agentic tool use upgrade

> "The AI has no agency — it can only reply, it can never act. If a customer says 'add the rose cream to my cart' in a natural way, Claude responds conversationally but the cart doesn't update. Add 4 tools Claude can actually call: add_to_cart(product_name, qty), show_menu(category), get_order_status(), save_address(address). Use the full agentic loop — execute the tool, feed the result back, let Claude write the final reply."

**Outcome:** Added `_TOOLS` to `ai_service.py`, `generate_reply` accepts `tool_executor` callback, agentic loop runs 2 API calls when tools fire. Four handler functions added to `whatsapp.py`. `_make_tool_executor` builds the closure with session/DB access. Session is persisted after tool calls via `ran_flag`.
