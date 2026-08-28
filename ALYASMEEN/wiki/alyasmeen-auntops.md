# ALYASMEEN AuntOps

**Summary**: Home page for the vault — a WhatsApp ordering bot for a natural & handmade skincare business in Palestine, with an AI conversation engine and a custom web dashboard.

**Sources**: raw/project-claude-md.md

**Graph**: [[graph-overview]] (whole-project map)

**Last updated**: 2026-06-14

---

ALYASMEEN AuntOps is a WhatsApp ordering bot for **ALYASMEEN**, a natural & handmade
skincare products business (lotions, creams, candles) in israel used for israeli arabs . Customers order via
WhatsApp in Arabic ; the aunt manages orders through a built-in web dashboard;
Claude Haiku powers the AI conversation. (source: raw/project-claude-md.md)

- **Owner:** Khaled (building it for his aunt)
- **Market:** Palestine · **Volume:** 10–30 orders/day
- **Languages:** Arabic (primary)

## How a message flows

A customer message hits [[whatsapp-bot-brain]], which checks **hard commands first**
(`cart`, `clear`, `pickup`, `delivery`, `confirm`, order tracking, numeric selection). If
nothing matches, it falls through to [[ai-service]] (Claude Haiku with 4 tools). On
`confirm`, the order is written to the database and the aunt gets a WhatsApp notification.
(source: raw/project-claude-md.md)

## Tech stack

- **Backend:** FastAPI (`uvicorn app.main:app`)
- **WhatsApp:** Meta Cloud API → [[whatsapp-meta-integration]]
- **AI:** Claude Haiku via Anthropic SDK → [[ai-service]]
- **Database:** Supabase (PostgreSQL over HTTPS) → [[supabase-data-layer]]
- **Dashboard:** custom FastAPI + Jinja2 UI → [[web-dashboard]]
- **Scheduler:** APScheduler jobs → [[scheduler-jobs]]

(graph: community "Tech Stack & Dependencies"; source: raw/project-claude-md.md)

## Project state (as of March 2026, per source)

- All 14 original improvement steps complete; AppSheet fully removed.
- Products live in the Supabase `products` table (not `catalog.json`).
- Hosted on Railway at `alyasmeen.org`; SSL cert and Meta WABA review pending.
- Knowledge base (`app/data/knowledge/`) is still empty — planned AI context.

_Time-sensitive: verify against the repo and live consoles before acting._

## Related pages

- [[whatsapp-bot-brain]]
- [[ai-service]]
- [[supabase-data-layer]]
- [[web-dashboard]]
- [[scheduler-jobs]]
- [[database-tables]]
- [[whatsapp-meta-integration]]
- [[graph-overview]]
