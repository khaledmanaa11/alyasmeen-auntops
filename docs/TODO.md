# TODO — ALYASMEEN AuntOps

**Date:** 2026-03-27
**Status:** Core development complete. Ready for deployment.

---

## Deployment

- [ ] Push codebase to a GitHub repository
- [ ] Create a new service on Railway or Render, linked to the GitHub repo
- [ ] Set all required environment variables on the hosting platform:
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
  - `DASHBOARD_PASSWORD`
  - `SECRET_KEY`
  - `AUNT_PHONE`
  - `CLAUDE_API_KEY`
- [ ] Set `USE_MOCK_WHATSAPP=0` (switch from mock to real Meta API)
- [ ] Verify the app starts without errors (check platform logs)
- [ ] Confirm the dashboard is accessible at `https://your-app-url/login`

---

## Real Products

- [ ] Open the `/products` dashboard page after deployment
- [ ] Add all real ALYASMEEN products with name, price, and description
- [ ] Note: `catalog.json` is a legacy file and is no longer used by the bot
- [ ] Products added via the dashboard are immediately visible to the WhatsApp bot
- [ ] Toggle any test/placeholder products to inactive or delete them

---

## WhatsApp Configuration

- [ ] Set `WA_META_TOKEN` — get from Meta Developer Portal -> App -> WhatsApp -> API Setup
- [ ] Set `WA_META_PHONE_ID` — the phone ID for the business number
- [ ] Set `WA_META_VERIFY_TOKEN` — a string you choose; used when registering the webhook
- [ ] (Optional) Set `WA_META_APP_SECRET` — for webhook signature verification
- [ ] Register the webhook URL in Meta Developer Portal:
  - URL: `https://your-app-url/whatsapp/webhook`
  - Verify token: same value as `WA_META_VERIFY_TOKEN`
  - Subscribe to: `messages`
- [ ] Test the webhook locally first using ngrok:
  - `ngrok http 8000`
  - Use the ngrok HTTPS URL as the webhook URL in Meta portal
  - Confirm the GET verification handshake succeeds
  - Send a WhatsApp message and confirm it hits the bot

---

## Knowledge Base

- [ ] Create `.md` files in `app/data/knowledge/` to give the AI more context
- [ ] Suggested files:
  - `store_info.md` — opening hours, location, contact info
  - `faq.md` — common customer questions and answers
  - `return_policy.md` — returns and exchange policy
  - `ingredients.md` — key ingredients and their skin benefits
- [ ] Each file is loaded once at startup and appended to the Claude system prompt
- [ ] Adding more relevant content improves the accuracy and quality of AI replies
- [ ] Files are read from `app/data/knowledge/**/*.md` (subdirectories supported)

---

## Completed

- [x] All 14 original improvement plan steps
- [x] Removed AppSheet entirely — replaced with custom web dashboard
- [x] Connected Supabase via HTTPS using `supabase-py` (no psycopg2, no pooler issues)
- [x] Orders page redesigned: customer name headline, inline products, WhatsApp link, status buttons
- [x] Aunt receives WhatsApp notification immediately when customer confirms an order
- [x] Post-delivery follow-up scheduler (every 6 hours)
- [x] Monthly report scheduler (1st of month, 8 AM, Arabic summary to aunt)
- [x] Retry queue for failed WhatsApp and invoice calls (every 15 minutes, max 3 attempts)
- [x] PDF invoice generated and sent to customer on order completion (replaced the earlier Wave invoicing approach — no external invoicing service is used)
- [x] Product management dashboard page (`/products`) — add, edit, toggle, delete
- [x] Products moved to Supabase `products` table (bot picks up changes instantly)
- [x] Broadcast messaging page (`/broadcast`) — send WhatsApp to customer segments
- [x] End-to-end local testing: orders API, dashboard stats, test order creation
