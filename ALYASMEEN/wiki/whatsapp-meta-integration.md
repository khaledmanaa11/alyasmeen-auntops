# WhatsApp Meta Integration

**Summary**: The outbound WhatsApp sender — real Meta Cloud API (`whatsapp_meta.py`) or a mock dev sender (`whatsapp_dev.py`) swapped by `USE_MOCK_WHATSAPP`. Also the inbound webhook.

**Sources**: raw/project-claude-md.md, app/services/whatsapp_meta.py, app/services/whatsapp_dev.py

**Graph**: communities "WhatsApp Meta Sender", "Mock WhatsApp Dev Sender"; god node `webhook_post()` (16 edges)

**Last updated**: 2026-06-14

---

Outbound messages go through one of two interchangeable senders, chosen by the
`USE_MOCK_WHATSAPP` env var (1 = mock prints to console, 0 = real Meta Cloud API).
(graph: hyperedge "Inbound WhatsApp message handling flow" → `concept_whatsapp_sender_swap`)

- **Real:** `app/services/whatsapp_meta.py` — Meta Cloud API, `webhook_post()` is the god
  node every send routes through.
- **Mock:** `app/services/whatsapp_dev.py` — prints to console for local dev.

## Webhook (inbound)

- GET verification fixed for dotted query params via `request.query_params`.
- The challenge returns `PlainTextResponse` (not JSON).
- Optional signature check via `WA_META_APP_SECRET`.

Verified messages are handed to [[whatsapp-bot-brain]].

## Env vars

`WA_META_TOKEN`, `WA_META_PHONE_ID`, `WA_META_VERIFY_TOKEN` (prod), `WA_META_APP_SECRET`
(optional). _Time-sensitive: Meta WABA review and the system-user token were pending in the
source — verify the live token before relying on real sends._

## Related pages

- [[whatsapp-bot-brain]]
- [[scheduler-jobs]]
- [[alyasmeen-auntops]]
- [[graph-overview]]
