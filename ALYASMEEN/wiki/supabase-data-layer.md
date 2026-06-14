# Supabase Data Layer

**Summary**: The single DB file (`app/db/database.py`) — talks to Supabase over HTTPS RPC (no psycopg2), with a retry + circuit-breaker seam. Home of the project's most-connected god nodes.

**Sources**: raw/project-claude-md.md, app/db/database.py

**Graph**: god nodes `query()` (40 edges), `execute()` (29), `execute_returning()` (14), `Config` (41); communities "Product Retriever & DB Client", "API Gatekeeper & Rate Limiting"

**Last updated**: 2026-06-14

---

`database.py` uses `supabase-py` over HTTPS — **not psycopg2**, no pooler. Two helper
functions live in Supabase: `run_query(sql)` (SELECT / INSERT…RETURNING via CTE) and
`run_exec(sql)` (INSERT / UPDATE / DELETE). All SQL uses `%s` placeholders, substituted by
`_escape()` + `_build()` before the RPC call — never f-strings (rule #3, SQL injection).
(source: app/db/database.py)

## The single seam: query / execute / execute_returning

Every DB call funnels through three public functions, which route through `_call()` — a
retry + circuit-breaker wrapper:

- **Reads** (`query`) retry transient failures with exponential backoff.
- **Writes** (`execute`, `execute_returning`) are **not** retried — a lost response after
  commit would double-apply.
- After enough consecutive failures the circuit **opens** and calls fail fast for a cooldown.

Tunables live in `config/rate_limits.json` under `"supabase"` (`max_retries`,
`retry_after_seconds`, `circuit_threshold`, `circuit_cooldown_seconds`) — never hardcoded.
(source: raw/project-claude-md.md)

These three functions are the graph's god nodes — almost everything touches them, which is
why `query()`/`execute()` top the connectivity ranking. (graph: god nodes)

## API gatekeeper

The community "API Gatekeeper & Rate Limiting" (`gatekeeper.py`, `ApiGatekeeper`,
`_load_rate_config()`) is the centralized external-API call manager — per-service rate
limit buckets, retries, and config loaded from `config/rate_limits.json`. (graph: community 1)

## Required env vars

`SUPABASE_URL`, `SUPABASE_KEY` (anon key). Rule #6: one DB file only — no direct supabase
imports elsewhere.

## Related pages

- [[database-tables]]
- [[whatsapp-bot-brain]]
- [[ai-service]]
- [[scheduler-jobs]]
- [[graph-overview]]
