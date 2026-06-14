# Design Decisions

**Summary**: The architectural decisions behind ALYASMEEN AuntOps — 9 accepted decisions distilled from the project's planning docs by `/gsd:ingest-docs`, plus the resolved conflicts between competing planning variants. This is the durable "why we built it this way" page; the volatile working copy lives in `.planning/intel/`.

**Sources**: .planning/intel/decisions.md, .planning/INGEST-CONFLICTS.md, .planning/intel/SYNTHESIS.md (synthesized by gsd-doc-synthesizer from docs/PLAN.md, docs/PLAN_PROMPT_ENGINEERING.md, docs/PRD*.md, docs/PROMPTS.md, docs/TODO*.md)

**Graph**: community "AI Service & Architecture Decisions"; hyperedge "Prompt engineering & data optimization sprint"

**Last updated**: 2026-06-14

---

These decisions were extracted from the `docs/` planning files and synthesized into
`.planning/intel/`. **No source doc is typed `ADR` and none carry `locked: true`** — every
decision is embedded inside a SPEC document (`PLAN.md`, `PLAN_PROMPT_ENGINEERING.md`) and is
recorded as **Accepted (not locked)**. Downstream consumers may promote any of these to a
standalone ADR. (source: .planning/intel/decisions.md)

> Provenance note: `.planning/` is GSD's volatile working memory. This page is the **durable**
> mirror — verify each decision against the live code in `../app/` before acting on it, exactly
> as the vault's citation rules require.

## Core architecture (from docs/PLAN.md)

- **ADR-001 — Supabase over direct PostgreSQL.** Connect via HTTPS using `supabase-py`; all
  SQL runs through two RPC functions (`run_query` for reads, `run_exec` for writes). No
  psycopg2, no pool config. *Why:* long-lived TCP connections time out / hit limits on
  Railway/Render. See [[supabase-data-layer]]. (source: .planning/intel/decisions.md, app/db/database.py)
- **ADR-002 — Claude Haiku as the AI model.** Smallest/fastest Claude; upgrade path to
  Sonnet/Opus via `CLAUDE_MODEL` env var with no code change. *Why:* strong Arabic, low
  cost per token, sub-second latency. See [[ai-service]]. (source: .planning/intel/decisions.md)
- **ADR-003 — FastAPI over Flask/Django.** *Why:* native async, Pydantic validation, OpenAPI
  docs, native Jinja2. (source: .planning/intel/decisions.md)
- **ADR-004 — SQL via Supabase RPC, not the supabase-py query builder.** `database.py`
  substitutes `%s` placeholders via `_escape()`/`_build()` before the RPC call. *Why:*
  readable/debuggable SQL with natural joins — the injection guard depends on `_escape()`,
  so never use raw f-strings. See [[supabase-data-layer]]. (source: .planning/intel/decisions.md, app/db/database.py)
- **ADR-005 — Agentic tool use via callback, not DB logic inside `ai_service.py`.**
  `generate_reply` takes an optional `tool_executor` closure that `whatsapp.py` supplies,
  keeping `ai_service.py` the single AI file with no DB/session imports. *Why:* preserves the
  "one AI file" rule; tool handlers live with the session state they need. See [[ai-service]]
  and [[whatsapp-bot-brain]]. (source: .planning/intel/decisions.md)

## Prompt-engineering sprint (from docs/PLAN_PROMPT_ENGINEERING.md)

- **ADR-PE-001 — Full catalog in the system prompt, not per-message retrieval.** Always inject
  the full active catalog as a `<catalog>` XML block. *Why:* a ≤30-product catalog ≈ 1,500
  tokens; always-include beats RAG on accuracy + latency at this size. Revisit past ~100
  products. **Supersedes** the inline per-message approach (see Resolved conflicts below).
  See [[ai-service]]. (source: .planning/intel/decisions.md)
- **ADR-PE-002 — XML-tagged system prompt.** Restructure with `<role>`, `<catalog_grounding>`,
  `<tool_rules>`/`<decision_tree>`, `<examples>`, `<reply_rules>`. *Why:* Haiku needs explicit
  if/then structure. (source: .planning/intel/decisions.md)
- **ADR-PE-003 — Trigger-based knowledge injection.** A `# triggers:` line per knowledge file;
  inject a file only when a trigger word appears, else fall back to always-on (no-trigger)
  files. *Why:* always-injecting 5 files adds ~2,500 irrelevant tokens/message; a vector store
  is overkill for 5 static files. **Supersedes** the load-all-at-startup approach. Ties to the
  still-empty `app/data/knowledge/` folder noted in [[ai-service]]. (source: .planning/intel/decisions.md)
- **ADR-PE-004 — Aliases column over fuzzy matching.** Add `aliases TEXT DEFAULT ''` to
  `products`; aunt registers synonyms; retriever does exact substring match. *Why:* explicit +
  deterministic, zero false positives; fuzzy matching is non-deterministic and error-prone in
  Arabic. See [[database-tables]]. (source: .planning/intel/decisions.md)

## Resolved conflicts (ingest, 2026-06-14)

`/gsd:ingest-docs` found two PRDs of equal precedence disagreeing, plus several
lower-precedence DOCs describing superseded designs. Both warnings were resolved
**user-approved on 2026-06-14** toward the SPEC-backed prompt-engineering variants.
(source: .planning/INGEST-CONFLICTS.md)

- **Catalog grounding** — `PRD.md` AI-05 (inline in the user message) vs `PRD_PE` CAT-01/03/04
  (full catalog in the system prompt). **Winner: full catalog in system prompt** (ADR-PE-001,
  SPEC-backed). PRD.md AI-05 marked superseded.
- **Token budget** — `PRD.md` AI-09 (`max_tokens=400` uniform) vs `PRD_PE` TOK-01 (600 with
  tools, 400 without). **Winner: 600/400 split.** PRD.md AI-09 marked superseded.
- Auto-resolved by precedence (SPEC/PRD > DOC): `PROMPTS.md` prompt-design principles and
  `TODO.md` knowledge-base layout both described the older design and are retained only as
  historical log. (source: .planning/intel/context.md)

## Invoicing mechanism — PDF only (resolved 2026-06-14, code-verified)

The ingest flagged a discrepancy: `PLAN.md` (SPEC) and `PRD.md` (DASH-18) document **only a
PDF invoice** on status → `done`, while `TODO.md` and the project `CLAUDE.md` also list **Wave
invoicing** as wired. **Settled against the live code: invoicing is PDF only.**

- There is **no `wave_invoice.py`** in the repo. `app/services/pdf_invoice.py` exists and its
  docstring states it *"replaces page_wave invoicing"*. (source: app/services/pdf_invoice.py:2)
- The invoice fires on status → `done` in `app/routers/ui_api.py:147`, calling
  `generate_invoice_pdf` and sending the PDF as a WhatsApp document. (source: app/routers/ui_api.py:147)
- Failures queue as the `pdf_invoice` retry action. (source: app/services/retry_actions.py:37)
- The only surviving "Wave" tokens are a **stale** retry-queue action comment in
  `schema.sql:90-93` and the optional `WAVE_*` env vars — neither is used by running code.

The Wave references in `TODO.md` and the project `CLAUDE.md` are **stale and should be
corrected**; they must not become a roadmap requirement. [[scheduler-jobs]] has been updated to
match. (source: .planning/INGEST-CONFLICTS.md INFO — RESOLVED)

## Related pages

- [[ai-service]]
- [[supabase-data-layer]]
- [[whatsapp-bot-brain]]
- [[scheduler-jobs]]
- [[database-tables]]
- [[alyasmeen-auntops]]
- [[graph-overview]]
