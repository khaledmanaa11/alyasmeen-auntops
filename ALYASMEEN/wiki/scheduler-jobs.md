# Scheduler Jobs

**Summary**: APScheduler background jobs wired in `app/main.py` — follow-ups, monthly report, retry queue — plus Wave invoicing on order completion.

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
| `retry_queue.process_retries` | every 15 min | retries failed WhatsApp/Wave calls (max 3×) | `app/services/retry_queue.py` |

## Wave invoicing

`wave_invoice.py` fires when an order status changes to `done`, producing a PDF invoice.
(graph: community "PDF Invoice Generator") Failures land in the [[supabase-data-layer]]
`retry_queue` table and are retried by the retry job. Env: `WAVE_API_KEY`,
`WAVE_BUSINESS_ID`, `WAVE_INCOME_ACCOUNT_ID` (all optional).

## Retry dispatch

The community "Retry Action Dispatch" handles re-sending failed WhatsApp messages and Wave
invoice calls, reading the `retry_queue` table. Each action is retried up to 3 times.

## Related pages

- [[whatsapp-meta-integration]]
- [[database-tables]]
- [[supabase-data-layer]]
- [[alyasmeen-auntops]]
