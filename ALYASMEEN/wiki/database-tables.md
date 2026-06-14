# Database Tables

**Summary**: The 8 Supabase tables (project `ppwcfmuetgczclmnzvqr`, ap-southeast-1) that hold products, customers, sessions, orders, and bot state.

**Sources**: raw/project-claude-md.md, app/db/schema.sql

**Graph**: anchors the "Product Retriever & DB Client" and "Database Layer Tests" communities; accessed only through [[supabase-data-layer]]

**Last updated**: 2026-06-14

---

All tables are reached exclusively through [[supabase-data-layer]]. (source: app/db/schema.sql)

| Table | Purpose |
|-------|---------|
| `products` | Product catalog — name, price, description, tags, aliases, active flag (live source of truth, replaced `catalog.json`) |
| `customers` | One row per customer — name, saved_address |
| `sessions` | WhatsApp cart + stage per customer (the state machine) |
| `orders` | Every confirmed order |
| `order_lines` | Line items inside each order |
| `chat_history` | AI conversation memory (last 6 turns sent to Claude — see [[ai-service]]) |
| `follow_ups` | Post-delivery follow-up tracking — see [[scheduler-jobs]] |
| `retry_queue` | Failed WhatsApp/Wave calls queued for retry — see [[scheduler-jobs]] |

## Products as live source of truth

The `products` table replaced the legacy `catalog.json`. The aunt edits it through the
`/products` page ([[web-dashboard]]); the bot picks up changes instantly via the retriever
(`invalidate_catalog()` clears the cache after any create/update/delete).
(graph: community "Product Retriever & DB Client")

## Related pages

- [[supabase-data-layer]]
- [[web-dashboard]]
- [[ai-service]]
- [[scheduler-jobs]]
- [[alyasmeen-auntops]]
