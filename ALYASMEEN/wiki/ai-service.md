# AI Service

**Summary**: The single AI file (`app/services/ai_service.py`) — Claude Haiku with 4 tools, product context, and chat history. Drives the conversation when no hard command matches.

**Sources**: raw/project-claude-md.md, app/services/ai_service.py

**Graph**: community "AI Service & Architecture Decisions"; hyperedges "Agentic tool-use loop" and "Prompt engineering & data optimization sprint"

**Last updated**: 2026-06-14

---

This is the **only** AI file in the project (rule #5). It calls Claude Haiku
(`claude-haiku-4-5-20251001` by default) with the product catalog injected, the last 6
turns of chat history, and 4 tools. (source: app/services/ai_service.py)

## The 4 tools

- `add_to_cart(product_name, qty)` — updates the cart in the DB
- `show_menu(category)` — loads products from Supabase, sets `menu_products` in session
- `get_order_status()` — queries the orders table
- `save_address(address)` — saves to customers + session

Tools execute inside [[whatsapp-bot-brain]], which has DB/session access.

## Agentic loop (2 API calls when a tool fires)

1. First call → Claude picks a tool (`stop_reason = "tool_use"`)
2. Tool runs in [[whatsapp-bot-brain]]
3. Result sent back to Claude as `tool_result`
4. Second call → Claude writes the conversational reply knowing what the tool returned

(graph: hyperedge "Agentic tool-use loop spanning AI service, callback, router and retriever")

## Knowledge base (planned)

The hyperedge "AI knowledge base injected into Claude context" points at
`app/data/knowledge/` — store info, ingredients FAQ, returns/shipping/skin advice. This
folder is **empty**; adding `.md` files there is an open to-do.
_Time-sensitive — verify before relying on it._

## Related pages

- [[whatsapp-bot-brain]]
- [[supabase-data-layer]]
- [[alyasmeen-auntops]]
- [[graph-overview]]
