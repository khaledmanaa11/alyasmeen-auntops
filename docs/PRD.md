# Product Requirements Document — ALYASMEEN AuntOps

**Version:** 1.0
**Date:** 2026-03-27
**Status:** Active

---

## 1. Project Overview

ALYASMEEN AuntOps is a WhatsApp ordering system for ALYASMEEN, a Palestinian small business selling natural and handmade skincare products: lotions, creams, and candles.

**Business context:**
- Location: Palestine
- Order volume: 10–30 orders per day
- Primary language: Arabic, with English support
- Sales channel: WhatsApp (no website or app)
- Management: Single owner (the aunt) managing orders solo

**Problem being solved:** The business was managing orders manually via WhatsApp messages and a spreadsheet. Orders were missed, customers had to wait for manual replies, and there was no way to track business performance. AuntOps automates the entire order flow and gives the owner a dashboard to manage everything.

---

## 2. Target Users

### Customer (End User)

- Arabic or English speaker
- Communicates via WhatsApp
- Wants to browse products, get personalized advice, place orders, and track delivery
- Expects fast, friendly, conversational replies — not a rigid form or menu system
- May not be tech-savvy; the bot must be forgiving of spelling variations and natural language

### Aunt (Business Owner)

- Manages the business alone
- Not a developer — needs a simple, visual web dashboard
- Needs to know immediately when a new order arrives (WhatsApp notification)
- Needs to update order status (prepared, out for delivery, done) and have customers notified automatically
- Needs to add/edit products without any technical knowledge
- Needs a monthly performance summary to understand business trends

---

## 3. Functional Requirements

### 3.1 WhatsApp Bot

| ID | Requirement |
|----|-------------|
| BOT-01 | Receive incoming WhatsApp messages via Meta Cloud API webhook |
| BOT-02 | Handle hard commands: `cart`, `clear`, `menu`, `pickup`, `delivery`, `confirm`, `info N` |
| BOT-03 | Handle Arabic order tracking: "وين طلبي" and similar phrases |
| BOT-04 | Handle number selection (`1`, `2`, `3`) from last shown product menu |
| BOT-05 | Handle quantity syntax (`2x1`, `3*2`) for adding multiple items |
| BOT-06 | Fall back to Claude Haiku AI for all unrecognized messages |
| BOT-07 | Greet new customers on their first message |
| BOT-08 | Persist cart, session stage, and address across restarts (Supabase `sessions` table) |
| BOT-09 | Save customer address for reuse in future delivery orders |
| BOT-10 | On `confirm`: write order + lines to Supabase, send confirmation to customer, notify aunt |
| BOT-11 | New-order notification to aunt includes: order number, customer name/phone, items, total, fulfillment type, address |
| BOT-12 | Order tracking reply includes: status label (Arabic), fulfillment type, order date |
| BOT-13 | Support both pickup and delivery fulfillment |

### 3.2 AI Conversation (Claude Haiku)

| ID | Requirement |
|----|-------------|
| AI-01 | Use Claude Haiku as the sole AI model |
| AI-02 | System prompt positions the AI as "عمة ALYASMEEN" — a friendly, knowledgeable skincare advisor |
| AI-03 | AI suggests only products from the Supabase catalog — no hallucinated products |
| AI-04 | AI detects language (Arabic/English) and replies in the same language |
| AI-05 | Product context (up to 6 matching products) is injected inline in the user message |
| AI-06 | Conversation history limited to last 6 turns to control token usage |
| AI-07 | Cart context injected into system prompt so AI can guide customer toward checkout |
| AI-08 | Knowledge base `.md` files from `app/data/knowledge/` are appended to system prompt |
| AI-09 | `max_tokens=400` keeps replies concise for WhatsApp format |
| AI-10 | AI gracefully degrades if `CLAUDE_API_KEY` is not set |
| AI-11 | AI is given 4 callable tools: `add_to_cart`, `show_menu`, `get_order_status`, `save_address` |
| AI-12 | When Claude calls a tool, the agentic loop executes: tool runs → result fed back → Claude writes final reply (2 API calls total) |
| AI-13 | Natural-language intents (e.g. "أضيفي كريم الورد للسلة") result in real cart/session mutations, not just conversational replies |
| AI-14 | `show_menu` tool sets `session.menu_products` so subsequent number selections (1, 2, 3) continue to work |
| AI-15 | Tool execution happens in `whatsapp.py` (has DB/session access); `ai_service.py` is tool-agnostic via the `tool_executor` callback |

### 3.3 Web Dashboard

| ID | Requirement |
|----|-------------|
| DASH-01 | Password-protected login using SHA-256 cookie session |
| DASH-02 | Orders page: list all orders with customer name, products inline, total, status |
| DASH-03 | Orders page: filter by status (all, to_do, ready, delivered, done) |
| DASH-04 | Orders page: one-click status update buttons that also send WhatsApp notification to customer |
| DASH-05 | Orders page: direct WhatsApp link to open chat with each customer |
| DASH-06 | Dashboard page: current month orders count and revenue |
| DASH-07 | Dashboard page: comparison with previous month |
| DASH-08 | Dashboard page: 30-day daily order bar chart |
| DASH-09 | Dashboard page: order status donut chart |
| DASH-10 | Dashboard page: top 5 products by quantity this month |
| DASH-11 | Products page: list all products with name, price, description, tags, active state |
| DASH-12 | Products page: create new product (name, price, description, tags) |
| DASH-13 | Products page: edit existing product inline |
| DASH-14 | Products page: toggle product active/inactive (inactive products hidden from bot) |
| DASH-15 | Products page: delete product |
| DASH-16 | Broadcast page: compose a WhatsApp message and send to a customer segment |
| DASH-17 | Broadcast segments: all customers, active last 30 days, top 10 by order count |
| DASH-18 | On status -> `done`: generate PDF invoice and send to customer via WhatsApp |

### 3.4 Background Scheduler

| ID | Requirement |
|----|-------------|
| SCHED-01 | Every 6 hours: check for customers whose order was delivered 3+ days ago and send follow-up |
| SCHED-02 | 1st of every month at 8 AM: send Arabic monthly summary to aunt's WhatsApp |
| SCHED-03 | Every 15 minutes: process retry queue for failed WhatsApp and invoice API calls |
| SCHED-04 | Retry queue: maximum 3 attempts per item before marking as failed |

---

## 4. Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Languages | Arabic (primary) + English — bot auto-detects per message |
| Response time | Bot reply to customer: < 2 seconds (p95) |
| Uptime | 99% availability |
| Test coverage | 85%+ coverage on core bot logic and API endpoints |
| Security | Dashboard password hashed with SHA-256; session via httponly cookie; no secrets in code |
| Data | All customer data (phone, name, address) stored in Supabase; no local files |
| Cost | Optimized for Supabase free tier and Claude Haiku (lowest cost Anthropic model) |
| Scalability | Designed for 10–30 orders/day; stateless FastAPI + Supabase can scale if needed |

---

## 5. User Stories

### Customer Stories

**US-01: Browse and order**
As a customer, I want to type a natural message like "عندي بشرة جافة" and get product recommendations, so I can find the right product without knowing the catalog.

Acceptance criteria:
- Bot passes message to Claude Haiku
- Claude searches active products from Supabase
- Reply includes 1–3 product recommendations with name, benefit, and price
- Reply is in the same language the customer used

**US-02: Add to cart**
As a customer, I want to type a number after seeing the menu to add that product to my cart.

Acceptance criteria:
- Menu shows products numbered 1, 2, 3...
- Typing `2` adds product #2 to the cart
- Typing `2x3` adds 2 of product #3
- Bot confirms addition and shows current cart total

**US-03: Check my cart**
As a customer, I want to type `cart` to see everything I've added and the total before paying.

Acceptance criteria:
- Cart displays product names, quantities, subtotals, and grand total in Arabic
- Cart shows even after the app restarts (persisted in Supabase)

**US-04: Place an order**
As a customer, I want to type `confirm` to place my order and get an order number.

Acceptance criteria:
- Order is saved to the database
- Customer receives confirmation message with order number
- Aunt receives notification immediately

**US-05: Track my order**
As a customer, I want to ask "وين طلبي" to see the status of my last order.

Acceptance criteria:
- Bot looks up the most recent order for that phone number
- Returns status in Arabic, fulfillment type, and order date

**US-06: Delivery address saved**
As a returning customer, I want the bot to remember my delivery address so I don't have to retype it.

Acceptance criteria:
- On first delivery, bot asks for and saves the address
- On next delivery order, bot offers the saved address
- Customer can override with a new address

### Aunt (Owner) Stories

**US-07: Instant new order alert**
As the business owner, I want to receive a WhatsApp message on my phone the moment a customer confirms an order, so I can start preparing it right away.

Acceptance criteria:
- Notification fires on every `confirm` within seconds
- Includes: order number, customer name + phone, item list, total, delivery or pickup
- For delivery orders, includes the customer's address
- Notification never prevents the order from being saved if it fails

**US-08: Manage order status**
As the business owner, I want to update an order status from the dashboard and have the customer notified automatically.

Acceptance criteria:
- Dashboard shows one clear action button per order based on current status
- Clicking the button updates status in database and sends WhatsApp to customer
- Customer message varies by fulfillment type (delivery vs. pickup wording)
- On `done`, a PDF invoice is generated and sent to the customer

**US-09: Add products without technical help**
As the business owner, I want to add a new product to the catalog from the dashboard without needing a developer.

Acceptance criteria:
- Products page has an "Add Product" form with name, price, description, tags
- New product is immediately available to the bot (no restart needed)
- Products can be toggled inactive without deleting them

**US-10: Monthly business summary**
As the business owner, I want to receive an Arabic WhatsApp summary on the 1st of each month showing my revenue and top products.

Acceptance criteria:
- Fires automatically at 8 AM on the 1st of each month
- Includes: total orders, total revenue, top products by quantity
- Written entirely in Arabic

---

## 6. Constraints

### Meta WhatsApp API

- Rate limit: 30 messages per minute per phone number
- Message templates required for outbound messages to users who haven't messaged in 24 hours
- Webhook must respond within 20 seconds or Meta retries
- Phone number must be verified in Meta Business Portal

### Supabase Free Tier

- 500 MB database storage
- 2 GB bandwidth per month
- Unlimited API requests
- No direct TCP connections — all queries via HTTPS using `supabase-py`

### Anthropic Claude Haiku

- API rate limits depend on tier
- `max_tokens=400` enforced to limit cost per message
- Context limited to last 6 turns of conversation history

---

## 7. Roadmap

### Phase 1 — Local Development (Complete)

- FastAPI backend with WhatsApp bot
- Supabase database integration
- Claude Haiku AI conversation
- Custom web dashboard (replacing AppSheet)
- Product management page
- Aunt new-order notifications
- Background scheduler (follow-up, monthly report, retry queue)
- PDF invoice on order completion
- Broadcast messaging

### Phase 2 — Deployment

- Push to GitHub
- Host on Railway or Render
- Set all production environment variables
- Switch `USE_MOCK_WHATSAPP=0`
- Configure Meta webhook URL

### Phase 3 — Real Products and WhatsApp

- Add real ALYASMEEN product catalog via `/products` dashboard
- Configure Meta WhatsApp business account
- Test full order flow end-to-end on real devices

### Phase 4 — Knowledge Base and Optimization

- Add `.md` files to `app/data/knowledge/` (store hours, FAQ, return policy, ingredient info)
- Monitor Claude token usage and tune prompt if needed
- Add multi-month historical view to dashboard
- Consider adding image support for product photos
