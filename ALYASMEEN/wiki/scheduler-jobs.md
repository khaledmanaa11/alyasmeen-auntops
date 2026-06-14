# Scheduler Jobs

**Summary**: APScheduler background jobs wired in `app/main.py` — follow-ups, monthly report, retry queue — plus a PDF invoice sent on order completion.

**Sources**: raw/project-claude-md.md, app/main.py, app/services/

**Graph**: communities "Follow-up Service", "Monthly Report & Webhook", "Retry Action Dispatch", "PDF Invoice Generator"

**Last updated**: 2026-06-14

---

Three recurring jobs run in the background, all registered in `app/main.py`.
(source: app/main.py)

| Job | Schedule | What it does | Module |
|-----|----------|--------------|--------|
| `followup.send_followups` | every 6 hours | follow-up to customers 3+ days after delivery | `app/services/followup.py` |
| `monthly_report.send_monthly_report` | 1st of month, 8 AM | Arabic monthly summary to `AUNT_PHONE` | `app/services/monthly_report.py` |
| `retry_queue.process_retries` | every 15 min | retries failed WhatsApp / PDF-invoice calls (max 3×) | `app/services/retry_queue.py` |

## PDF invoicing

When an order's status changes to `done`, `app/routers/ui_api.py` generates a PDF invoice via
`generate_invoice_pdf` and sends it to the customer as a WhatsApp document.
(source: app/routers/ui_api.py:147, app/services/pdf_invoice.py) (graph: community "PDF
Invoice Generator") Failures are queued in the [[supabase-data-layer]] `retry_queue` table
(action `pdf_invoice`) and retried by the retry job.

> **No Wave integration exists.** `pdf_invoice.py:2` states it "replaces page_wave invoicing".
> The only "Wave" tokens left in the repo are a stale retry-queue action comment in
> `schema.sql:90-93` and optional `WAVE_*` env vars in the project brief — none are used by
> running code. See [[design-decisions]] (invoicing question, resolved 2026-06-14). The
> `WAVE_API_KEY` / `WAVE_BUSINESS_ID` / `WAVE_INCOME_ACCOUNT_ID` env vars are vestigial.

## Retry dispatch

`app/services/retry_actions.py` re-sends failed WhatsApp messages and PDF invoices, reading
the `retry_queue` table. Each action is retried up to 3 times. (source: app/services/retry_actions.py:37)

## Related pages

- [[whatsapp-meta-integration]]
- [[database-tables]]
- [[supabase-data-layer]]
- [[alyasmeen-auntops]]
