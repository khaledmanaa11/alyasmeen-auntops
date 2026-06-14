# WhatsApp Bot Brain

**Summary**: The message router (`app/routers/whatsapp.py`) — intercepts hard commands, manages the cart/session state machine, writes orders, and notifies the aunt; falls through to AI when nothing matches.

**Sources**: raw/project-claude-md.md, app/routers/whatsapp.py

**Graph**: [[graph-overview#Community Hubs (navigation)]] — community "WhatsApp Bot Brain & Sessions"; god node `_phone()` (18 edges)

**Last updated**: 2026-06-14

---

Every inbound WhatsApp message lands here first. The brain checks **hard commands before
AI** — if the message matches one, the handler runs and Claude is never called.
(source: app/routers/whatsapp.py)

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
