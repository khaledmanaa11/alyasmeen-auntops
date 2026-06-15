# WhatsApp Bot Brain

**Summary**: The message router (`app/routers/whatsapp.py`) — intercepts hard commands, manages the cart/session state machine, writes orders, and notifies the aunt; falls through to AI when nothing matches.

**Sources**: raw/project-claude-md.md, app/routers/whatsapp.py

**Graph**: [[graph-overview#Community Hubs (navigation)]] — community "WhatsApp Bot Brain & Sessions"; god node `_phone()` (18 edges)

**Last updated**: 2026-06-15

---

Every inbound WhatsApp message lands here first. The brain checks **hard commands before
AI** — if the message matches one, the handler runs and Claude is never called.
(source: app/routers/whatsapp.py)

## Inbound logging is encoding-safe

The first thing `webhook_post` does is log the inbound message via the module logger —
`log.info("WHATSAPP RX from=%s name=%s text=%s", phone, wa_name, text)`, not a bare
`print`. This matters because the bot is Arabic-first: on a Windows dev console (cp1255) a
bare `print` of Arabic/emoji raises `UnicodeEncodeError`, and since this runs before any
processing it would drop the whole message. The logger swallows handler emit errors (it
never re-raises), and `app/main.py` reconfigures `sys.stdout`/`sys.stderr` to
`encoding="utf-8", errors="replace"` at startup so the line also renders correctly. Linux/
Railway stdout is already UTF-8; this only bit local Windows testing.
(source: app/routers/whatsapp.py, app/main.py)

## Hard commands

| Command | Effect |
|---------|--------|
| `cart` | show cart |
| `clear` | empty cart |
| `pickup` | set fulfillment to pickup |
| `delivery` | ask for address, save to DB |
| `confirm` | write order, confirm to customer, notify aunt |
| `وين طلبي` | look up latest order status |
| number / `2x1`, `3*2` | add product (with quantity) from the last menu |

## New-order notification to the aunt

Fires on every `confirm`: an Arabic summary (order ID, customer, line items, total,
fulfillment, address) is sent to `AUNT_PHONE`. It only fires if `AUNT_PHONE` is set and is
wrapped in try/except — a failed notification never fails the order.
(source: raw/project-claude-md.md)

## Fall-through to AI

When no hard command matches, the brain calls [[ai-service]]. Tools that Claude picks
(add_to_cart, show_menu, get_order_status, save_address) execute back here, because this
module holds full DB and session access. See the agentic loop in [[ai-service]].

## Related pages

- [[ai-service]]
- [[supabase-data-layer]]
- [[whatsapp-meta-integration]]
- [[database-tables]]
- [[alyasmeen-auntops]]
