# ALYASMEEN AuntOps

A WhatsApp ordering bot + web dashboard for ALYASMEEN — a natural & handmade skincare business in Palestine.

---

## Overview

ALYASMEEN AuntOps is a complete order management system built for a small Palestinian skincare business selling lotions, creams, and candles. Customers place orders by chatting in Arabic or English on WhatsApp. The business owner manages everything through a clean web dashboard without needing any third-party tools.

**Key features:**

- WhatsApp bot handles the full order flow: browsing, cart, address, confirmation
- Claude Haiku AI provides conversational product advice in Arabic and English — and can now **take real actions** (add to cart, show menu, look up order status, save address) via tool calls
- The aunt receives a WhatsApp notification the moment a customer confirms an order
- Web dashboard for order management, product catalog, business stats, and bulk messaging
- Automatic follow-up messages 3 days after delivery
- Monthly business summary sent to the aunt on the 1st of each month
- PDF invoice generated and sent to customers on order completion
- Failed message retries handled automatically in the background

---

## Installation

### Prerequisites

- Python 3.10 or newer
- pip
- A Supabase project (free tier works)
- An Anthropic API key (for Claude Haiku)

### Steps

1. **Download or clone the project**

   ```bash
   git clone <repo-url>
   cd auntops_fixed
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   ```bash
   cp .env.example .env
   ```

   Open `.env` and fill in the required values (see Configuration Guide below).

4. **Minimum required vars for local development**

   ```
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your_anon_key
   DASHBOARD_PASSWORD=any_password_you_choose
   SECRET_KEY=a_long_random_string
   CLAUDE_API_KEY=sk-ant-...
   USE_MOCK_WHATSAPP=1
   ```

   With `USE_MOCK_WHATSAPP=1`, all WhatsApp messages are printed to the console — no Meta account needed for local dev.

---

## Running Locally

Start the server:

```bash
uvicorn app.main:app --reload --port 8000
```

Access the dashboard: [http://localhost:8000/login](http://localhost:8000/login)

Create a test order (simulates a customer confirming):

```bash
curl -X POST http://localhost:8000/dev/test_order
```

With `USE_MOCK_WHATSAPP=1`, all outgoing WhatsApp messages are printed to the terminal — you can see exactly what customers and the aunt would receive.

---

## Bot Flow

```
Customer sends WhatsApp message
        |
  Hard commands checked first
        |
   "cart"         -- show current cart with totals
   "clear"        -- empty the cart
   "menu"         -- show numbered product list
   "pickup"       -- set fulfillment to in-store pickup
   "delivery"     -- ask for delivery address (saves for next order)
   "confirm"      -- write order to database, notify aunt
   "وين طلبي"    -- look up latest order status
   "1", "2", "3" -- add product from last shown menu
   "2x1", "3*2"  -- add product with specific quantity
   "info 1"       -- show full details for product #1
        |
   No match -> Claude Haiku AI (agentic)
        |
        ├── tool: add_to_cart(product_name, qty)   -> cart actually updated in DB
        ├── tool: show_menu(category)               -> live Supabase products, numbered list
        ├── tool: get_order_status()                -> real order lookup from DB
        └── tool: save_address(address)             -> saved to customer record + session
        |
   Claude writes final reply with tool results -> Arabic/English reply sent
```

When Claude uses a tool, **two API calls** are made: one for Claude to decide the action, one for Claude to write the reply after seeing the result. This means natural messages like "أضيفي كريم الورد للسلة" or "شو عندكم من شموع؟" now actually update state, not just reply conversationally.

**New customer:** On first message, the bot greets them and introduces the store.

**Order confirmation flow:**

1. Customer browses products and adds items to cart
2. Customer types `delivery` or `pickup`
3. For delivery, bot asks for address (saved for future orders)
4. Customer types `confirm`
5. Order is saved to database
6. Customer receives order confirmation with order number
7. Aunt receives a WhatsApp notification immediately with full order details

---

## Dashboard

Log in at [http://localhost:8000/login](http://localhost:8000/login) with your `DASHBOARD_PASSWORD`.

### Pages

| URL | Description |
|-----|-------------|
| `/login` | Password login (Arabic UI) |
| `/orders` | Order list — customer name, inline products, status buttons, WhatsApp link |
| `/dashboard` | Monthly stats, 30-day order chart, status breakdown, top 5 products |
| `/products` | Add, edit, toggle active/inactive, delete products |
| `/broadcast` | Send a WhatsApp message to customer segments |

### Order Status Labels

| Code | Arabic label | Meaning |
|------|-------------|---------|
| `to_do` | يجب التجهيز | New order, needs preparation |
| `ready` | جاهز | Ready for pickup / out for delivery |
| `delivered` | في الطريق | Delivered to customer |
| `done` | مكتمل | Order complete, invoice sent |

When status changes, the customer receives an automatic WhatsApp notification. When status reaches `done`, a PDF invoice is generated and sent to the customer.

### Broadcast

The `/broadcast` page allows sending a custom WhatsApp message to:

- **All customers** — everyone in the database
- **Active (last 30 days)** — customers who ordered in the past month
- **Top 10** — customers with the most orders

---

## Configuration Guide

| Variable | Required | Purpose |
|----------|----------|---------|
| `SUPABASE_URL` | Yes | Supabase project URL (`https://xxx.supabase.co`) |
| `SUPABASE_KEY` | Yes | Supabase anon key (from Project Settings -> API) |
| `DASHBOARD_PASSWORD` | Yes | Web dashboard login password |
| `SECRET_KEY` | Yes | Session cookie signing — use a long random string |
| `AUNT_PHONE` | Yes | Owner's WhatsApp number for order alerts and monthly report (format: `972591234567`) |
| `CLAUDE_API_KEY` | Yes | Anthropic API key for AI replies |
| `CLAUDE_MODEL` | No | Default: `claude-haiku-4-5-20251001` |
| `USE_MOCK_WHATSAPP` | No | `1` = mock (console output), `0` = real Meta API. Default: `1` |
| `WA_META_TOKEN` | Production | WhatsApp sender token from Meta Developer Portal |
| `WA_META_PHONE_ID` | Production | WhatsApp phone ID from Meta Developer Portal |
| `WA_META_VERIFY_TOKEN` | Production | Webhook verification token (you choose this value) |
| `WA_META_APP_SECRET` | Optional | Webhook signature verification |

---

## Deployment (Railway / Render)

1. **Push to GitHub**

   ```bash
   git add .
   git commit -m "initial deploy"
   git push
   ```

2. **Create a new service** on Railway or Render, pointing to your GitHub repo.

3. **Set environment variables** in the platform dashboard:
   - Minimum: `SUPABASE_URL`, `SUPABASE_KEY`, `DASHBOARD_PASSWORD`, `SECRET_KEY`, `AUNT_PHONE`, `CLAUDE_API_KEY`
   - Set `USE_MOCK_WHATSAPP=0` for production

4. **Set WhatsApp variables:**

   ```
   WA_META_TOKEN=...
   WA_META_PHONE_ID=...
   WA_META_VERIFY_TOKEN=...
   ```

5. **Configure Meta webhook URL** in the Meta Developer Portal:

   ```
   https://your-app-url.railway.app/whatsapp/webhook
   ```

6. **Add real products** using the `/products` dashboard page. The `catalog.json` file is no longer used — products live in the Supabase `products` table.

7. **Add knowledge base files** (optional): drop `.md` files into `app/data/knowledge/` for richer AI responses (store hours, FAQ, policies, etc.).

---

## Project Structure

```
auntops_fixed/
├── app/
│   ├── main.py                  # FastAPI app + APScheduler startup
│   ├── routers/
│   │   ├── whatsapp.py          # Bot brain -- all WhatsApp message handling
│   │   ├── ui.py                # Web dashboard + JSON APIs
│   │   └── debug.py             # Dev endpoints (POST /dev/test_order)
│   ├── templates/
│   │   ├── login.html
│   │   ├── orders.html
│   │   ├── dashboard.html
│   │   ├── products.html
│   │   └── broadcast.html
│   ├── services/
│   │   ├── config.py            # All env vars
│   │   ├── ai_service.py        # Claude Haiku integration (single AI file)
│   │   ├── followup.py          # Post-delivery follow-up scheduler
│   │   ├── monthly_report.py    # Monthly Arabic summary to aunt
│   │   ├── pdf_invoice.py       # PDF invoice generation
│   │   ├── retry_queue.py       # Failed API call retry handler
│   │   ├── whatsapp_meta.py     # Real WhatsApp sender (Meta Cloud API)
│   │   └── whatsapp_dev.py      # Mock WhatsApp sender (console output)
│   ├── ai/
│   │   └── retriever.py         # Product search from Supabase
│   ├── db/
│   │   ├── database.py          # Supabase HTTPS client (supabase-py)
│   │   └── schema.sql           # DB schema reference
│   └── data/
│       ├── catalog.json         # Legacy -- not used; products in Supabase
│       └── knowledge/           # AI knowledge base -- add .md files here
├── tests/
├── .env                         # Secrets -- never commit
├── .env.example                 # Template for .env
├── Procfile                     # uvicorn start command for Railway/Render
└── requirements.txt
```

---

## Contributing

**Code style:** This project uses `ruff` with a 100-character line limit.

```bash
pip install ruff
ruff check app/
ruff format app/
```

**Running tests:**

```bash
uv run pytest tests/
# or
pytest tests/
```

**Key rules when contributing:**

- Never hardcode secrets — use `Config.VARIABLE_NAME` from `app/services/config.py`
- Never commit `.env`
- SQL parameters always use `%s` placeholders — never f-strings
- One AI file only: `app/services/ai_service.py`
- One database file only: `app/db/database.py` — no direct `supabase` imports elsewhere
- Arabic text in UI is intentional — do not translate without discussion

**Pull requests:**

- One feature or fix per PR
- Add or update tests for any changed behavior
- Include a short description of what changed and why

---

## License

MIT License. See LICENSE file for details.
