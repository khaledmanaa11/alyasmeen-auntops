# Graph Overview (Layer 2)

**Summary**: Obsidian mirror of the graphify knowledge graph for ALYASMEEN AuntOps — the structural skeleton that seeds the wiki.

**Sources**: ../graphify-out/GRAPH_REPORT.md, raw/graphify-report-snapshot.md

**Generated**: 2026-06-14 — AUTO-DERIVED, do not hand-edit. Re-sync from graphify instead.

---

> This is Layer 2: machine-extracted structure, not curated truth. It tells the wiki
> *what to write about*. Curated prose lives in [[index|the wiki]].

## Stats

- **787 nodes · 1211 edges · 58 communities** (41 shown, 17 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 46 inferred edges (avg confidence 0.62)
- Corpus: 109 files

## God Nodes — core abstractions (most connected)

Each god node is a candidate for its own wiki page. Linked to where it has been written up.

| # | Node | Edges | Wiki home |
|---|------|-------|-----------|
| 1 | `Config` | 41 | [[supabase-data-layer]] / config |
| 2 | `query()` | 40 | [[supabase-data-layer]] |
| 3 | `execute()` | 29 | [[supabase-data-layer]] |
| 4 | `Random` | 18 | _(test/data generation)_ |
| 5 | `_phone()` | 18 | [[whatsapp-bot-brain]] |
| 6 | `webhook_post()` | 16 | [[whatsapp-meta-integration]] |
| 7 | `_is_authenticated()` | 15 | [[web-dashboard]] |
| 8 | `execute_returning()` | 14 | [[supabase-data-layer]] |
| 9 | `Request` | 14 | [[web-dashboard]] |
| 10 | `run_pipeline()` | 13 | _(multi-agent pipeline)_ |

## Community Hubs (navigation)

The named clusters graphify found. Bold ones have a curated wiki page.

- **WhatsApp Bot Brain & Sessions** → [[whatsapp-bot-brain]]
- **AI Service & Architecture Decisions** → [[ai-service]]
- **Product Retriever & DB Client** → [[supabase-data-layer]], [[ai-service]]
- **Web Dashboard UI Router** → [[web-dashboard]]
- **API Gatekeeper & Rate Limiting** → [[supabase-data-layer]]
- **Database Layer Tests** → [[supabase-data-layer]]
- **Follow-up Service** → [[scheduler-jobs]]
- **Monthly Report & Webhook** → [[scheduler-jobs]]
- **Retry Action Dispatch** → [[scheduler-jobs]], [[supabase-data-layer]]
- **PDF Invoice Generator** → [[scheduler-jobs]]
- **WhatsApp Meta Sender** → [[whatsapp-meta-integration]]
- **Mock WhatsApp Dev Sender** → [[whatsapp-meta-integration]]
- **Intent Eval & Broadcast AI** → [[ai-service]]
- **Tech Stack & Dependencies** → [[alyasmeen-auntops]]
- Multi-Agent Pipeline · Frontend Pipeline · Noise Dataset Generator — _no wiki page yet_
- 25+ test communities (AI Service Tests, Config Tests, Bot Flow Integration Tests, …) —
  mirror the modules they cover; not given separate wiki pages.

## Surprising connections

Non-obvious links graphify inferred — worth a callout in the relevant page.

- `Catalog editor HTML tool` —semantically similar to→ `Supabase (PostgreSQL over HTTPS RPC)`
  (catalog_editor.html ↔ INTEGRATIONS.md) — the standalone editor mirrors the live data layer.
- `Path`, `AsyncAnthropic` —use→ `Config` (both agent pipelines depend on central config).

## Hyperedges (group relationships)

Multi-node relationships — each maps to a "how it fits together" section in the wiki.

- **AI knowledge base injected into Claude context** — store/ingredients/returns/shipping/skin
  knowledge + Claude API → see [[ai-service]] (knowledge base is empty; planned).
- **Inbound WhatsApp message handling flow** — session state machine, agentic tool executor,
  sender swap, DB adapter → see [[whatsapp-bot-brain]].
- **Agentic tool-use loop** spanning AI service, callback, router, retriever → [[ai-service]].
- **Five dashboard templates sharing the premium RTL design system** → [[web-dashboard]].
- **Prompt engineering & data optimization sprint** (catalog injection, XML prompt, aliases) → [[ai-service]].

## Import cycles

- 1-file self-cycle: `tests/data/eval_intent.py` (benign).

## Related pages

- [[index]]
- [[alyasmeen-auntops]]
