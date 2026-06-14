# Web Dashboard

**Summary**: The aunt-facing web UI (`app/routers/ui.py` + `app/templates/`) — login, orders, dashboard stats, and product management, sharing one premium RTL design system.

**Sources**: raw/project-claude-md.md, app/routers/ui.py, app/templates/

**Graph**: community "Web Dashboard UI Router"; god nodes `_is_authenticated()` (15 edges), `Request` (14); hyperedge "Five dashboard templates sharing the premium RTL design system"

**Last updated**: 2026-06-14

---

A custom FastAPI + Jinja2 dashboard replaced AppSheet entirely. (source: app/routers/ui.py)

## Pages

| URL | What it does |
|-----|--------------|
| `/login` | Password login (Arabic RTL) |
| `/orders` | Order list — customer name headline, inline products, WhatsApp link, action buttons |
| `/dashboard` | Monthly stats, 30-day chart, status donut, top 5 products |
| `/products` | Add / edit / toggle / delete products |
| `/logout` | Clear session |

JSON APIs back each page (`/api/orders`, `/api/dashboard/stats`, `/api/products`, …).

## Auth

Cookie = SHA-256 of `SECRET_KEY:DASHBOARD_PASSWORD`; checked by `_is_authenticated()` — a
god node because every protected route depends on it. (graph: god node `_is_authenticated()`)

## Design system

All five templates (login, orders, dashboard, products, broadcast) share one premium RTL
design language — primary green `#006948`, Material Symbols icons, glassmorphism navbar,
20px-radius cards. Do not revert to the old `#059669` green or DaisyUI classes.
(graph: hyperedge "Five dashboard templates sharing the premium RTL design system";
source: raw/project-claude-md.md)

## Order status labels (Arabic)

`to_do` → يجب التجهيز · `ready` → جاهز · `delivered` → في الطريق · `done` → مكتمل

## Related pages

- [[database-tables]]
- [[supabase-data-layer]]
- [[alyasmeen-auntops]]
- [[graph-overview]]
