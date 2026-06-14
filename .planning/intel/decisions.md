# Decisions (synthesized intel)

Architecture decisions extracted from the ingested docs. No doc in this set is typed `ADR` and none carry `locked: true` — every decision below is **embedded inside a SPEC document** (`PLAN.md`, `PLAN_PROMPT_ENGINEERING.md`). Status is recorded as **Accepted (not locked)**. Downstream consumers may promote these to standalone ADRs.

---

## ADR-001 — Supabase over direct PostgreSQL connection
- source: docs/PLAN.md (§5, embedded in SPEC)
- status: Accepted (not locked)
- scope: database connectivity
- decision: Use Supabase as DB host, connect via HTTPS using `supabase-py`. All SQL runs through two Supabase RPC functions (`run_query` for SELECT, `run_exec` for writes). No psycopg2, no connection pool config.
- rationale: psycopg2 long-lived TCP connections time out / hit limits on Railway/Render.

## ADR-002 — Claude Haiku as the AI model
- source: docs/PLAN.md (§5, embedded in SPEC)
- status: Accepted (not locked)
- scope: AI model selection
- decision: Use Claude Haiku (smallest/fastest Claude model). Upgrade path to Sonnet/Opus via `CLAUDE_MODEL` env var with no code change.
- rationale: strong Arabic support, low cost/token, sub-second latency.

## ADR-003 — FastAPI over Flask or Django
- source: docs/PLAN.md (§5, embedded in SPEC)
- status: Accepted (not locked)
- scope: web framework
- decision: Use FastAPI for webhook + dashboard.
- rationale: native async, Pydantic validation, OpenAPI docs, native Jinja2.

## ADR-004 — SQL via Supabase RPC instead of the supabase-py query builder
- source: docs/PLAN.md (§5, embedded in SPEC)
- status: Accepted (not locked)
- scope: data access pattern
- decision: Write raw SQL executed via `run_query` / `run_exec`; `database.py` substitutes `%s` placeholders via `_escape()`/`_build()` before the RPC call.
- rationale: readable/debuggable SQL, natural joins/aggregations; SQL-injection guard depends on `_escape()` — never use raw f-strings.

## ADR-005 — Agentic tool use via callback instead of embedding DB logic in ai_service.py
- source: docs/PLAN.md (§5, embedded in SPEC)
- status: Accepted (not locked)
- scope: AI tool-use architecture
- decision: `generate_reply` accepts an optional `tool_executor: Callable[[str, dict], str]`. The caller (`whatsapp.py`) supplies a closure capturing `phone`, `st`, `cart` and routes tool calls to handlers there. `ai_service.py` stays the single AI file with no DB/session imports.
- rationale: preserves "one AI file" rule; tool handlers live with the session state they need; each tool call costs one extra API call (a real per-message cost to monitor as volume grows).

## ADR-PE-001 — Full catalog in system prompt vs. per-message retrieval
- source: docs/PLAN_PROMPT_ENGINEERING.md (§4, embedded in SPEC)
- status: Accepted (not locked)
- scope: AI product grounding (SUPERSEDES the inline per-message approach in PLAN/PRD/PROMPTS — see conflicts)
- decision: Always inject the full active catalog into the Claude system prompt as a `<catalog>` XML block, regardless of message content. Rejected per-message keyword retrieval (had a zero-grounding silent-failure mode).
- rationale: ≤30-product catalog ≈ 1,500 tokens; always-include beats RAG on accuracy + latency at this size. Revisit past ~100 products.

## ADR-PE-002 — XML-tagged system prompt
- source: docs/PLAN_PROMPT_ENGINEERING.md (§4, embedded in SPEC)
- status: Accepted (not locked)
- scope: system prompt structure
- decision: Restructure the system prompt with XML section tags (`<role>`, `<catalog_grounding>`, `<tool_rules>`/`<decision_tree>`, `<examples>`, `<reply_rules>`).
- rationale: Haiku needs explicit if/then structure; XML gives each instruction distinct scope and priority.

## ADR-PE-003 — Trigger-based knowledge injection
- source: docs/PLAN_PROMPT_ENGINEERING.md (§4, embedded in SPEC)
- status: Accepted (not locked)
- scope: knowledge base injection (SUPERSEDES the load-all-at-startup approach in TODO.md/PROMPTS.md)
- decision: Parse a `# triggers:` line per knowledge file; inject a file only when a trigger word appears in the current message; fall back to always-on (no-triggers) files otherwise.
- rationale: always-injecting 5 files adds ~2,500 irrelevant tokens per message; vector retriever is overkill for 5 static files.

## ADR-PE-004 — Aliases column over fuzzy matching in code
- source: docs/PLAN_PROMPT_ENGINEERING.md (§4, embedded in SPEC)
- status: Accepted (not locked)
- scope: bilingual product retrieval
- decision: Add `aliases TEXT DEFAULT ''` to the `products` table; aunt registers synonyms; retriever does exact substring match against aliases. Rejected Levenshtein/phonetic matching.
- rationale: explicit + deterministic, zero false positives; fuzzy matching is non-deterministic and error-prone in Arabic.
