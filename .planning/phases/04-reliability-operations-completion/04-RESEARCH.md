# Phase 4: Reliability & Operations Completion - Research

**Researched:** 2026-08-25
**Domain:** Durable messaging (outbox), synchronous rate limiting, Supabase key/RLS model, APScheduler persistence, Supabase backup/restore CLI
**Confidence:** HIGH (call-site inventory, DB schema, CLI behavior all directly verified in this repo/environment). MEDIUM on Railway/production network specifics (documented, not directly tested against the live deployment).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Decisions (LOCKED — user chose these explicitly)

1. **Delete `retry_queue.py`** (and `retry_actions.py` if nothing else uses it after migration).
   The outbox (`outbox_jobs` + `process_outbox_jobs`) becomes the single retry mechanism.
   Scheduler services (PDF invoice on done, follow-ups, monthly report) must enqueue into
   `outbox_jobs` instead of calling senders directly + queueing failures into `retry_queue`.
   Note: this needs a new outbox job kind for PDF invoices (payload can't hold raw bytes —
   store order_id and regenerate the PDF in `process_job`, or store a reference). Remove the
   `retry_queue` table from active use (drop or deprecate via migration comment) and the
   15-min scheduler job.

2. **Rewrite `gatekeeper.py` synchronous and wire it in.** The user explicitly wants real
   rate limiting on outbound Claude and Meta calls (chose this over deletion). Requirements:
   - Synchronous API callable from the worker's blocking loops (no asyncio).
   - Bounded waiting — must never stall the single worker indefinitely (the current
     unbounded `while not bucket.is_allowed(): sleep(...)` loop is unacceptable; fail or
     defer the job instead).
   - Config stays in `config/rate_limits.json` (services: `claude_ai`, `whatsapp`).
   - Wire into `ai_service.generate_reply`/`improve_message` (Claude) and the four
     `whatsapp_meta` senders (Meta). Keep the existing unit tests' intent; port them to
     the sync API.

3. **Switch the app to the Supabase `service_role` key.**
   - Railway env `SUPABASE_KEY` will hold the service_role key (user action; plan must
     include the checklist item and verification step).
   - Revert the anon re-grant: new migration that revokes EXECUTE on `run_query`/`run_exec`
     from `anon`/`authenticated` again (undoing `20260825000001_fix_rpc_grants.sql`),
     leaving RLS locked for anon. Document the decision in the migration header and
     CLAUDE.md's DB section.
   - Local dev/.env gets the service_role key too (single code path).

### Claude's Discretion

- Dead-letter dashboard UX: where the dead-lettered `webhook_events` and failed
  `outbox_jobs` surface (existing orders page card vs. new tab), and the retry interaction —
  follow the existing design system (#006948, Material Symbols, Arabic RTL).
- Outbox kind/payload design for invoice jobs.
- How the worker-restart persistence check is verified (script vs documented manual drill).
- Backup drill execution details (Supabase CLI vs dashboard export) — but the drill must
  actually run and the Drill Log must record a real result.

### Deferred Ideas (OUT OF SCOPE)

- MFA / session hardening (Phase 5), CSRF, security headers.
- Policy gate / handoffs / eval harness (Phase 3).
- CI/CD pipeline (tracked for go-live phase).
- The 69MB `tests/data/whatsapp_agent_dataset_noisy.json` in git history (flagged during
  push; cleanup is a separate chore, not a Phase 4 criterion).
</user_constraints>

## Summary

Phase 4 is a **consolidation/deletion phase**, not a new-feature phase — nearly everything
needed is already partially built (outbox tables exist, gatekeeper logic exists, migrations
exist), and the job is to finish wiring one seam (outbox), rewrite one seam (gatekeeper), and
flip one config value (service_role) — each with a precise, small blast radius that I traced
call-site by call-site in the actual repo. Two of the four research-focus mechanics I was
asked to verify (Supabase CLI Docker dependency, and `db push`/`db dump` behavior) I tested
directly against the installed `npx supabase` 2.115.0 CLI in this environment rather than
relying on documentation, because the docs are inconsistent/stale on this exact point and
`docs/BACKUP_DRILL.md` itself is blocked on a wrong assumption ("drill pending Docker
availability").

**Key discovery (HIGH confidence, directly verified):** the currently-installed Supabase CLI
(`npx supabase`, v2.115.0) does **not** require Docker for `supabase link`, `supabase db push`,
or `supabase db dump` — running each with `--dry-run` in this Windows/no-Docker environment
fails with `LegacyProjectNotLinkedError` (a credentials/linking error), never a Docker error.
Docker is only needed for local-dev-stack commands (`db start`, `db diff`, `db pull`) which
Phase 4 does not need. This unblocks both the "apply migrations to the live project" success
criterion and the backup/restore drill — no Docker install required on Windows.

**Primary recommendation:** migrate `queue_text`/`queue_buttons` (already the pattern in
`app/services/processor.py`) into `followup.py`, `monthly_report.py`, and the three inline
sends in `ui_api.py`'s status-update handler; add one new outbox kind (`pdf_invoice`, payload
`{"order_id": ...}`) to `process_job()`; delete `retry_queue.py`/`retry_actions.py` and their
two test files; rewrite `gatekeeper.py` as a plain sync class with a *capped, short* wait
(not the full `retry_after_seconds` from config) before failing fast, since the existing
retry surfaces (outbox `attempts`/`max_attempts`, AI fallback reply) already provide the
actual retry/defer mechanism; use the Supabase **Session Pooler** connection string (not
direct connection, not Transaction Pooler) for `DATABASE_URL` so APScheduler's
`SQLAlchemyJobStore` survives Railway's default IPv4-only outbound networking; and apply the
`service_role`-switch + RLS-revert migration in the strict order: (1) get the new key into
env everywhere the app runs, (2) verify the app works with `service_role` while the anon
re-grant is *still active* (so a mistake doesn't cause a full outage), (3) only then ship the
revoke migration.

## Call-Site Inventory: Outbox Migration (Decision 1)

Every place that currently sends a WhatsApp message or generates a PDF invoice, verified by
reading the actual files (not assumed):

| File | Function | Current behavior | What it must become |
|------|----------|-------------------|----------------------|
| `app/services/followup.py:66` | `send_followups()` | Calls `send_text(phone, FOLLOWUP_MESSAGE)` directly; wraps in `try/except: log.exception` (no retry at all today — a failure is just logged and dropped) | `queue_text(phone, FOLLOWUP_MESSAGE)` — an `execute()` INSERT into `outbox_jobs`, no try/except needed for the send itself (durability now lives in the poller) |
| `app/services/monthly_report.py:156` | `send_monthly_report()` | Calls `send_text(Config.AUNT_PHONE, report)` directly; `try/except: log.exception` | `queue_text(Config.AUNT_PHONE, report)` |
| `app/routers/ui_api.py:124` (`ready`) | status-update endpoint | `send_text(phone, msg)` inline in the HTTP request handler; failure silently swallowed (`except Exception: logger.warning(...)`) | `queue_text(phone, msg)` |
| `app/routers/ui_api.py:134` (`delivered`) | status-update endpoint | `send_text(phone, ...)` inline, same swallow pattern | `queue_text(phone, ...)` |
| `app/routers/ui_api.py:149-177` (`done`) | status-update endpoint | `send_text` (thank-you) **and** inline `generate_invoice_pdf()` + `send_document_bytes()`, both swallowed on failure | `queue_text(...)` for the thank-you; enqueue a new `pdf_invoice` job (see below) for the invoice |
| `app/services/retry_actions.py:37-73` | `execute_action("pdf_invoice", ...)` | The only place that currently regenerates + sends a PDF from a queued retry; this logic is the template to port | Move this body (order/lines lookup → `generate_invoice_pdf` → `send_document_bytes`) into `process_job()`'s new `elif kind == "pdf_invoice":` branch |
| `app/services/processor.py:180-191` | `process_job()` | Already dispatches `whatsapp_message` / `whatsapp_buttons` by `kind` | Add third branch: `elif kind == "pdf_invoice":` |
| `app/worker.py:29,35` | `start_worker()` | Imports `process_retries` from `retry_queue`, schedules it every 15 min | Delete both lines; drop `"retry_queue"` from the `jobs=[...]` log list |

**Outbox job design for invoices (Claude's discretion — recommendation):**
```python
# Enqueue (in ui_api.py's "done" branch, replacing the inline generate+send):
execute(
    "INSERT INTO outbox_jobs (kind, phone, payload) VALUES (%s, %s, %s)",
    ("pdf_invoice", phone, {"order_id": order_id}),
)
```
```python
# process_job() new branch — mirrors retry_actions.execute_action("pdf_invoice", ...):
elif kind == "pdf_invoice":
    order_id = payload.get("order_id")
    rows = query(
        "SELECT o.id, o.phone, c.name AS customer_name FROM orders o "
        "LEFT JOIN customers c ON c.phone = o.phone WHERE o.id = %s", (order_id,),
    )
    customer_name = (rows[0]["customer_name"] or "") if rows else ""
    lines = query(
        "SELECT product_name, qty, unit_price FROM order_lines WHERE order_id = %s",
        (order_id,),
    )
    total = sum(float(ln["unit_price"]) * int(ln["qty"]) for ln in lines)
    pdf_bytes = generate_invoice_pdf(order_id, customer_name, date.today().strftime("%d/%m/%Y"), lines, total)
    send_document_bytes(phone, pdf_bytes, filename=f"فاتورة-{order_id}.pdf", caption=f"🧾 فاتورتك لطلب رقم {order_id}")
```
Storing `order_id` (not the PDF bytes, not a pre-rendered URL) means invoice content is always
regenerated fresh from current order data at send time — correct even if the job sits in the
queue retrying for a while, and keeps `outbox_jobs.payload` small (JSONB column, no reason to
carry ~30-80KB of PDF bytes through it).

**Order-of-operations note:** in `ui_api.py`, today the order-status `UPDATE` runs
*unconditionally after* the (try/excepted) send — status changes even if the WhatsApp send
failed. After migrating to `queue_text`/enqueue, the INSERT into `outbox_jobs` essentially
never fails synchronously (it's just a DB write, and `execute()` already has retry/circuit-
breaker for the RPC layer) — so the status update ordering is preserved with less special-
casing. Deciding whether an outbox INSERT failure should now surface as a 500 to the operator
(vs. today's silent swallow) is a planning decision, not a research one — flagging it because
today's swallow is one of the causes of "invisible failure" the phase goal names.

**Test files that exclusively test the code being deleted** (verified — no other production
code imports `retry_queue`/`retry_actions` besides `worker.py`):
- `tests/unit/test_retry.py` — tests `retry_queue.enqueue/process_retries` and
  `retry_actions.execute_action` (non-PDF actions). Delete.
- `tests/unit/test_retry_actions_pdf.py` — tests the PDF action specifically. Delete, but
  **port its assertions** (PDF bytes returned, correct filename, correct total) into a new
  test for `process_job(kind="pdf_invoice", ...)`.

**Tests that need updated mocking after the migration** (currently monkeypatch `send_text`
directly on the module — will need to instead assert an `outbox_jobs` row was inserted, or
use `flush_outbox()` + `sent_messages` from `tests/conftest.py`'s existing `mock_db` fixture,
which already exists for exactly this pattern in the processor tests):
- `tests/unit/test_followup.py` (5 tests patch `fu.send_text`)
- `tests/unit/test_monthly_report.py` (patches `mr.send_text` in 2 tests)
- `tests/integration/test_orders_api.py` (`test_update_to_ready_succeeds`,
  `test_update_to_delivered_succeeds` patch `wa_dev.send_text`)

**`retry_queue` table:** CONTEXT.md says "drop or deprecate via migration comment" — given
Phase 4 also touches migrations for the service_role/RLS revert, the cheapest safe choice is
a new migration that documents retry_queue's retirement, drops its RLS policy reference (it's
already covered by the blanket `ENABLE ROW LEVEL SECURITY` + no policies = deny-all, so no
functional risk in leaving the table itself in place) — **do not `DROP TABLE`** in the same
phase that also touches grants/RLS; a dead, empty, RLS-locked table is zero-risk, whereas a
`DROP TABLE` is irreversible and untestable against a live prod DB in this repo's current
setup. Recommend: leave the table, stop all reads/writes to it, note the retirement in the
migration header (matching the existing `20260825000001` self-documenting style).

## Synchronous Gatekeeper Design (Decision 2)

**Current problem (verified in `app/shared/gatekeeper.py`):** `execute()` is `async def`,
called with `await`, and on rate-limit it does:
```python
while not bucket.is_allowed():
    await asyncio.sleep(retry_after)   # retry_after = 10s (claude_ai) or 30s (whatsapp)
```
No caller in the codebase currently calls `gatekeeper.execute()` at all — it is 100% dead
code today (confirmed: `grep -rn "gatekeeper"` shows zero call sites outside the file itself
and its docstring example). `tests/unit/test_gatekeeper.py` runs it via
`asyncio.get_event_loop().run_until_complete(...)`.

**Where it must be wired in** (verified exact call sites):
- `app/services/ai_service.py:401` and `:431` — `client.messages.create(...)` inside
  `generate_reply()` (the agentic loop makes up to 2 calls per turn: pick-tool, then
  final-reply). Both need gatekeeper wrapping under service key `"claude_ai"`.
- `app/services/ai_service.py:492` — `client.messages.create(...)` inside
  `improve_message()` (broadcast-improvement AI call). Same service key.
- `app/services/whatsapp_meta.py` — 4 senders, each does its own `requests.post(...)`:
  `send_text` (line 48), `send_buttons` (line 88), `send_document_bytes` (2 POSTs: media
  upload line 104, then send line 123), `send_document` (line 168). Service key `"whatsapp"`.
  (`send_document_bytes` makes *two* HTTP calls — gatekeeper should wrap each, or wrap the
  whole function; wrapping each POST is more accurate to "per API call" but wrapping the
  function once is simpler and the upload+send pair is inherently sequential/atomic from the
  caller's perspective — recommend wrapping the whole function for simplicity, since the two
  calls always happen together and rate-limiting only one half doesn't protect against the
  other.)

**Callers of the above** (why bounded waiting matters — verified via `app/worker.py`):
`ai_service.generate_reply` runs inside `processor.handle_message()`, itself invoked from
`process_webhook_events()`, an APScheduler job on a **3-second interval**.
`whatsapp_meta` senders run inside `processor.process_job()`, invoked from
`process_outbox_jobs()`, on a **2-second interval**. Both are `BlockingScheduler` interval
jobs with APScheduler's documented defaults: `ThreadPoolExecutor(10)` and (per APScheduler
3.x defaults) `max_instances=1` per job — so a job instance that blocks past its next
scheduled fire is *skipped*, not queued, meaning a long synchronous sleep inside the
gatekeeper directly causes missed 2s/3s polls (the bot going quiet, outbox draining slower).
This is the concrete mechanism behind the "must never stall the single worker indefinitely"
requirement — it is not hypothetical.

**Recommended design — capped sleep, not job-deferral-via-reschedule:**

The config's `retry_after_seconds` (10s for `claude_ai`, 30s for `whatsapp`) is calibrated for
the *old* async/unbounded design and is **incompatible** with the worker's 2-3s poll cadence
— sleeping even one full `retry_after_seconds` inside the calling thread already blows past
several poll intervals. Rather than build a second deferral mechanism (e.g., scheduling a
delayed re-run), reuse the retry/defer machinery that **already exists** in the outbox
(`attempts`/`max_attempts`/`status='failed'`, re-polled every 2s) and in `ai_service`'s
existing fallback-on-exception path:

```python
class RateLimitExceeded(RuntimeError):
    """Raised when a service's rate limit is still exceeded after the bounded wait."""

class ApiGatekeeper:
    def execute(self, service: str, api_call: Callable, *args,
                max_wait: float = 2.0, poll_interval: float = 0.25, **kwargs) -> Any:
        bucket = self._bucket(service)
        waited = 0.0
        while not bucket.is_allowed() and waited < max_wait:
            time.sleep(poll_interval)
            waited += poll_interval
        if not bucket.is_allowed():
            raise RateLimitExceeded(f"{service} rate limit exceeded after {waited:.1f}s wait")

        bucket.record()
        try:
            return api_call(*args, **kwargs)
        except Exception:
            raise  # let the existing caller-side retry surface handle it
```

- `max_wait` defaults small (order-of-seconds, well under the 2s outbox / 3s webhook poll
  interval — e.g. 1-2s) so the *absolute worst case* added latency per call is bounded and
  small, satisfying "never stall indefinitely" without needing a new config knob per call site.
- No internal retry-on-failure loop in the gatekeeper itself (the old code retried
  `max_retries` times with exponential backoff *inside* `execute()`) — that duplicates retry
  logic that already exists one layer up (outbox `attempts`, AI fallback reply) and is exactly
  the kind of nested-retry-storm that makes latency unpredictable. Recommend the gatekeeper
  do **rate-limit admission control only** (wait-briefly-then-fail-fast), and let the existing
  callers' existing exception handling do what they already do:
  - `ai_service.generate_reply`/`improve_message`: already wrapped in `try/except Exception`
    that returns the Arabic fallback string or raises to the caller — a `RateLimitExceeded`
    falls through the same path with no new code needed in `processor.py`.
  - `process_job()`: already wrapped in `try/except Exception` that sets
    `status='failed', last_error=str(e)` — a `RateLimitExceeded` here is picked up by the
    outbox poller's own retry loop on the next 2s cycle, which **is** the "defer" behavior
    the context note asks for, for free.
- At current volume (10-30 orders/day, well under 30rpm/500rph for `whatsapp` and
  50rpm/1000rph for `claude_ai`), the bucket should essentially never be full in production —
  this is a correctness/safety-net path, not a hot path, so the small fixed `max_wait` has
  negligible real-world cost.
- Port `tests/unit/test_gatekeeper.py` off `asyncio.run_until_complete` onto plain sync calls;
  keep the bucket/window tests as-is (`_ServiceBucket` logic is unchanged), and add a test for
  the new bounded-wait-then-`RateLimitExceeded` behavior (e.g., fill the bucket, call
  `execute()` with a small `max_wait`, assert it raises within roughly `max_wait`, not longer).

## Supabase `service_role` Key Switch (Decision 3)

**Why this exists (verified from migration headers):** `20260614000003_security_rls.sql`
enabled RLS and revoked `run_query`/`run_exec` execute grants from `anon`/`authenticated`.
`app/db/database.py`'s `_get_client()` builds the Supabase client from `Config.SUPABASE_KEY`
— documented in CLAUDE.md as the **anon key**. That combination meant the app had zero DB
access after that migration; `20260825000001_fix_rpc_grants.sql` re-granted execute to
`anon`/`authenticated` as a stopgap, and its own header already names the two durable fixes:
(a) move to `service_role` server-side, or (b) replace the two generic SQL RPCs with typed
per-operation RPCs. Phase 4 locks in (a).

**Mechanically, what changes:** nothing in `app/db/database.py` itself — it already just
reads `Config.SUPABASE_KEY` and passes it to `create_client()`. The `service_role` key
carries the Postgres `service_role`, which has the `bypassrls` attribute — RLS policies
(`FOR ALL TO service_role USING (true)`, already present on every app table per
`20260614000003_security_rls.sql`) become moot once the key itself bypasses RLS, but the
grants on `run_query`/`run_exec` still matter: those two functions are plain SQL functions,
not policies, so `service_role` needs `EXECUTE` on them too. `service_role` has superuser-like
privileges in Postgres by default in Supabase's role model, but do not assume — explicitly
verify: `service_role` already has default `EXECUTE` on functions it doesn't need an explicit
grant for in most Supabase setups, but since `20260614000003` did a blanket `REVOKE ... FROM
anon, authenticated, public` (not `service_role`), `service_role`'s access was never revoked
in the first place — the anon-re-grant migration was only ever needed because the app was
using the anon key. **This means the revert migration (revoking anon/authenticated again)
is safe to ship independently of whether `service_role`'s grant needs restating** — it never
lost it.

**Security context (MEDIUM confidence, industry-standard guidance, not Supabase-specific
verification):** service_role keys bypass RLS entirely and are equivalent to root DB access;
they must never be sent to a browser/client and must only be constructed server-side (exactly
this app's shape — `database.py` runs only inside the FastAPI/worker processes on Railway,
never shipped to the dashboard's HTML/JS). This matches the plan already implied by
`20260825000001`'s own header.

**Recommended safe sequencing (the research-focus question) — verified against what actually
breaks at each step, by reading `database.py` and the migrations in order:**

1. **Set the new key in every place the app reads `SUPABASE_KEY` from**, *while the anon
   re-grant migration (`20260825000001`) is still live* (do not revoke anon/authenticated
   yet). This is Railway env vars (`SUPABASE_KEY`) and local `.env`. At this point the app
   works with `service_role` (which never lost its grants) — a config-only change, zero SQL
   run, fully reversible by flipping the env var back.
2. **Verify E2E with the new key before touching any migration** — hit `/health` (exercises
   `ping()` → `query()` → `run_query` RPC), then a full order flow (webhook → cart → confirm →
   `create_order_atomic` RPC → outbox send) against the **live** Supabase project. This is the
   point where a wrong key, wrong grants, or wrong RLS policy would surface as a real error —
   and because anon still has access too, a failure here is diagnosable/rollback-able without
   any customer-facing outage (the anon path is still technically live as a fallback until
   step 3, even though the app itself now only uses `service_role`).
3. **Only after step 2 passes, ship the revoke migration** (new migration undoing
   `20260825000001` — revoke `EXECUTE` on `run_query(text)`/`run_exec(text)` from
   `anon, authenticated` again). This is the point of no return for the anon path; doing it
   first (before verifying the app works on `service_role`) is exactly the mistake
   `20260825000001`'s header describes happening once already ("the app has had no way to
   reach the database at all").

**What breaks if done out of order:** revoking anon/authenticated *before* confirming
`SUPABASE_KEY` is actually `service_role` everywhere the app runs (Railway **and** local, per
the locked decision) reproduces the exact outage `20260825000001` was written to fix — total
DB unreachability, since the RPC-grant is the only thing standing between "app has a key" and
"app can call the two RPCs every single DB operation in this codebase goes through."

**CLAUDE.md update needed:** the "Required env vars" table currently documents
`SUPABASE_KEY=<anon key>` — Phase 4 must update this line and add a short note (mirroring
`20260825000001`'s own honesty) explaining why `service_role` is required and that it must
never be exposed to the dashboard's client-side code.

## APScheduler `SQLAlchemyJobStore` Persistence (Success Criterion 3)

**Current state (verified in `app/worker.py`):** `DATABASE_URL` is read from `Config`; if
unset, the scheduler falls back to the default in-memory `MemoryJobStore` (jobs don't survive
a restart — this is the literal "Worker job store falls back to MemoryJobStore" risk item in
STATE.md). If set, `SQLAlchemyJobStore(url=Config.DATABASE_URL)` is used. `psycopg2-binary`
and `sqlalchemy>=2.0.0` are both already in `requirements.txt` — no new dependency needed.

**What actually needs persisting, in this app's case:** APScheduler's job *definitions*
(the 4-5 `add_job(...)` calls with `id=...`), not job *execution history* — they're re-added
with `replace_existing=True` on every worker boot anyway. The practical value of
`SQLAlchemyJobStore` here is narrower than it sounds: it mainly protects `next_run_time`
bookkeeping for the `cron`-scheduled `monthly_report` job across restarts (so a restart near
the 1st doesn't cause a missed or duplicate fire) — the `interval` jobs (webhook/outbox
pollers, every 2-3s) barely notice a restart either way since they just resume on the next
tick. This context is useful for planning the "worker-restart persistence check" (Claude's
discretion): the meaningful thing to verify is that a job's `next_run_time` (specifically
`monthly_report`, the cron job) is unchanged across a worker restart, not that "jobs run" (they
always would, restart or not, given `replace_existing=True` re-adds them).

**Connection-string caveat (HIGH confidence — directly verified against current official
Supabase docs, and directly relevant because this app deploys to Railway):** Supabase exposes
three connection endpoints, and the choice matters for a long-running `BlockingScheduler`
process on Railway:

| Type | Port | Host pattern | IPv4/IPv6 | Fit for this worker |
|------|------|--------------|-----------|----------------------|
| Direct connection | 5432 | `db.<ref>.supabase.co` | **IPv6 only**, unless the paid IPv4 add-on is purchased | Works only if Railway's outbound IPv6 is explicitly enabled (off by default per Railway docs) or the IPv4 add-on is bought. Otherwise DNS/connect silently fails. |
| Session Pooler (Supavisor) | 5432 | `aws-<region>.pooler.supabase.com`, username `postgres.<project-ref>` | IPv4, all tiers | **Recommended** — IPv4-compatible, supports persistent/long-lived connections and prepared statements, matches "persistent backend" use case Supabase's own docs name explicitly. |
| Transaction Pooler (Supavisor) | 6543 | same host, different port | IPv4, all tiers | Not recommended — transaction mode does not support prepared statements and expects short-lived/ephemeral connections (serverless/edge use case), a mismatch for a long-running `BlockingScheduler` process. |

Railway's outbound networking is **IPv4-only by default**; outbound IPv6 is an explicit
opt-in toggle per service (confirmed via Railway's own docs, current as of their 2026-07
changelog). This means the Direct Connection string will very likely fail to resolve/connect
from a default Railway deployment — **use the Session Pooler connection string for
`DATABASE_URL`**, not the one that superficially looks "simpler" (direct, port 5432 on the
`db.<ref>.supabase.co` host).

**Other verified pitfalls:**
- SQLAlchemy 1.4+ (and therefore 2.0, which this repo pins) **rejects** the `postgres://`
  scheme outright (`NoSuchModuleError`) — Supabase's dashboard-provided connection strings
  already use `postgresql://`, so this only bites if someone hand-edits or copies from an
  older example. Worth a one-line note in the deployment checklist: copy the connection string
  verbatim from the Supabase dashboard, don't hand-type it.
- Always include `?sslmode=require` (or confirm the pooler enforces TLS by default — Supabase
  connections are TLS-required regardless, but being explicit avoids ambiguity for anyone
  reading the connection string later).
- `DATABASE_URL` is a distinct value from `SUPABASE_URL`/`SUPABASE_KEY` (the HTTPS/PostgREST
  path used by `app/db/database.py`) — these are two separate connection paths to the same
  database (`supabase-py` via HTTPS RPC for the app's own queries, raw Postgres via SQLAlchemy
  only for APScheduler's job store). Do not conflate them; `DATABASE_URL` requires the
  database password (found in Supabase dashboard → Settings → Database), which is a different
  secret from `SUPABASE_KEY`.

## Backup & Restore Drill Mechanics (Success Criterion 5)

**Directly tested in this environment (HIGH confidence — not documentation, actual command
output):**
```
$ docker --version
bash: docker: command not found

$ npx supabase db push --dry-run --linked
{"_tag":"Error","error":{"code":"LegacyProjectNotLinkedError","message":"Cannot find project ref. Have you run supabase link?"}}

$ npx supabase db dump --dry-run --linked -f test_dump.sql
{"_tag":"Error","error":{"code":"LegacyProjectNotLinkedError","message":"Cannot find project ref. Have you run supabase link?"}}
```
Neither command errors on Docker — both get past any Docker check straight to a
linking/credentials error. This directly contradicts `docs/BACKUP_DRILL.md`'s own status line
("Drill pending Docker availability") and some third-party blog commentary claiming `db dump`
"runs pg_dump in a container." The installed CLI (a native Go binary, not a Docker-wrapped
script, as of v2.115.x) does not need Docker for remote-only operations — Docker is required
only for `supabase start` (local dev stack) and schema-diffing commands (`db diff`, `db pull`),
none of which Phase 4's backup/restore work needs.

**What Phase 4 needs to actually run the drill (recommended concrete sequence):**
1. `npx supabase link --project-ref ppwcfmuetgczclmnzvqr` (prompts for/accepts `-p` DB
   password — this is the Postgres password from Supabase dashboard → Settings → Database,
   the same one that composes `DATABASE_URL` above).
2. `npx supabase db push --linked` — applies every not-yet-applied migration file in
   `supabase/migrations/` to the live project, tracked via the
   `supabase_migrations.schema_migrations` history table. This directly satisfies "all
   supabase/migrations applied to the live project" (success criterion 2) — no Docker, no
   manual dashboard SQL-editor pasting (which `REQ-prod-migrations` explicitly says to avoid:
   "no direct dashboard edits").
3. `npx supabase db dump --linked -f backup_<date>.sql` (schema+data) and
   `npx supabase db dump --linked --role-only -f roles_<date>.sql` — matches
   `docs/BACKUP_DRILL.md`'s already-documented commands, now unblocked.
4. **Restore target — recommendation:** create a second, throwaway **free-tier** Supabase
   project (free tier costs nothing, and a restore drill's entire point is proving the backup
   file is usable against a real Postgres/Supabase instance, not just any local Postgres —
   this also matches `docs/BACKUP_DRILL.md`'s own "Disaster Recovery Plan" section, which
   already assumes a fresh project). `npx supabase link --project-ref <new-ref>`, then
   `npx supabase db push --linked` (schema/migrations) followed by loading the data dump —
   since `db push` only applies *migration files*, not arbitrary dump SQL, the data-only dump
   needs a direct `psql` load: `psql "<new-project-session-pooler-url>" -f backup_<date>.sql`
   (requires native `psql`/`pg_dump` client tools on Windows — install via the PostgreSQL
   Windows installer from EnterpriseDB, which is a plain `.exe`, no Docker, no WSL; on Windows
   `pg_dump`/`psql`/`pg_restore` end up under
   `C:\Program Files\PostgreSQL\<version>\bin\` and are usually **not** added to `PATH`
   automatically — the plan should call this out explicitly).
5. **Verification queries** (already specified in `docs/BACKUP_DRILL.md` step 3 — reuse
   as-is): row counts on `products`/`orders` matching production, spot-check recent `orders`
   rows, confirm `audit_logs` present.
6. **Record the result in the Drill Log table** already present at the bottom of
   `docs/BACKUP_DRILL.md` — replace the current `N/A / "drill pending Docker availability"`
   row with a real date/result/notes row. This satisfies "Drill Log records success" literally
   — the table already exists, it just needs a truthful entry.
7. Delete the throwaway restore-target project afterward (free tier, no ongoing cost, but no
   reason to leave a second copy of real customer data sitting around).

**Free vs Pro tier (MEDIUM confidence, general Supabase documentation, not verified against
this specific project's current plan):** Supabase's own managed daily backups (7-day
retention, accessible via Dashboard → Database → Backups) are a **Pro-tier-only** feature —
the free tier includes no automated managed backups at all. This makes the CLI-based manual
`db dump` procedure above not just a nice-to-have but the **only** backup mechanism available
unless the project is confirmed to be on Pro. The plan should explicitly note which tier the
live project is on (not found in the repo — this is a fact to confirm with the user/Supabase
dashboard, not something inferrable from code) since it changes whether "automated off-site
backups" (REQ-prod-backup-restore) needs a scheduled CLI job (e.g., a cron/GitHub Action
running `db dump` weekly, per `docs/BACKUP_DRILL.md`'s existing "Manual (Off-site / Local)"
section) or can lean on Supabase's own Pro-tier daily backups as the primary and the CLI dump
as the off-site copy.

## Dead-Letter Dashboard (Success Criterion 4)

**Exact queries verified against the schema (`webhook_events` in
`20260614000001_durable_messaging.sql` + `attempts` column in `20260825000000`; `outbox_jobs`
in the same baseline migration):**

Dead-lettered webhook events (poison-pilled after `MAX_WEBHOOK_EVENT_ATTEMPTS = 3`, per
`process_webhook_events()` in `processor.py`):
```sql
SELECT id, phone, payload, error, attempts, created_at
FROM webhook_events
WHERE processed = TRUE AND error LIKE 'dead-letter:%'
ORDER BY created_at DESC
```
(The `dead-letter:` prefix is written verbatim by `process_webhook_events()` — safe to match on.)

Terminally-failed outbox jobs (excluded from the poller's own re-pickup query,
`WHERE status IN ('pending','failed') AND attempts < max_attempts`, so `attempts >=
max_attempts` is the dead state):
```sql
SELECT id, kind, phone, payload, last_error, attempts, max_attempts, created_at
FROM outbox_jobs
WHERE status = 'failed' AND attempts >= max_attempts
ORDER BY created_at DESC
```

**Retry mutation — recommendation (research-focus question: reset row vs. new row):**
**Reset the existing row in place**, not insert a new one, for both tables — this matches the
mutation style already used everywhere else in this codebase (`retry_queue`'s own
`UPDATE ... SET resolved = TRUE`, `outbox_jobs`' own status-transition updates in
`process_job()`), and preserves the row's `created_at`/history for audit purposes rather than
fragmenting it across two rows. Neither table has a dedup/idempotency key that would make
inserting a new row safer (that's `webhook_events.wamid`'s job, and a manual retry from the
dashboard doesn't have a new `wamid` to give it anyway).
```sql
-- webhook_events retry:
UPDATE webhook_events SET processed = FALSE, attempts = 0, error = NULL WHERE id = %s
-- outbox_jobs retry:
UPDATE outbox_jobs SET status = 'pending', attempts = 0, last_error = NULL, updated_at = now() WHERE id = %s
```

**Important caveat to surface to the operator (not fixable within Phase 4's scope — flagging,
not solving):** resetting `webhook_events.processed = FALSE` causes `handle_message()` to
re-run from scratch. The `wamid` unique constraint prevents the *same inbound WhatsApp message*
from being inserted twice, but it does **not** make the bot logic itself idempotent at the
command level — e.g., if the original processing got as far as calling `confirm` and
`create_order_atomic` succeeded, but a later step in that same `handle_message()` call threw
(e.g., the aunt-notification `queue_text`), retrying would re-run `_handle_confirm()` against
whatever the session state is *now*, which may no longer have the cart that produced the
original order (it's cleared via `clear_session()` right after `create_order_atomic()` in the
success path — so in practice the highest-risk double-order scenario is already narrow, but
not zero, e.g. if the failure happens between `create_order_atomic()` and `clear_session()`).
Full command-level idempotency (an idempotency key per processed side-effect) is
`REQ-prod-idempotency`-adjacent but deeper than what's currently built (message-level dedup
only) — out of scope for Phase 4 per the locked decisions, but the dashboard's retry-button
copy/tooltip should say something like "قد يكرر هذا بعض الإجراءات إذا فشلت الرسالة الأصلية
جزئياً" (this may repeat some actions if the original message partially failed) so the
operator isn't surprised. This is a genuine, currently-real gap — not a hypothetical.

**UI placement (Claude's discretion — recommendation):** the existing dashboard has 4 tabs
(`Orders`, `Dashboard`, `Products`, `Broadcast`, from `app/routers/ui.py`'s routes) sharing one
`nav-glass` navbar defined identically in every template (verified in `orders.html`). Dead-
lettered items are a distinct operational concern from daily order management (low frequency,
technical-failure-focused, not something the aunt needs to see every day) — recommend a 5th
nav tab (e.g. `/alerts`, Arabic label "تنبيهات" with a Material Symbols `warning` icon) rather
than embedding into `/orders` (which is already dense — customer name headline, inline
products, action buttons per `orders.html`) or `/dashboard` (stats-focused, would need new
layout patterns for per-row retry buttons vs. its current chart/stat-card layout). A new tab
reuses 100% of the existing design system (card CSS classes, nav-glass, Cairo font, Material
Symbols, RTL) already defined identically across all 5 templates — no new visual pattern to
invent, just a new template + route following the exact same shell as `products.html` (which
already has the closest-matching UX: a list of rows, each with inline action buttons, e.g.
toggle/delete).

## Common Pitfalls

### Pitfall 1: Retry-after values calibrated for the deleted async design
**What goes wrong:** Porting `gatekeeper.py`'s existing `retry_after_seconds` values (10s,
30s) directly into a synchronous `time.sleep()` inside a 2-3s-interval worker loop.
**Why it happens:** The values were written for an `asyncio.sleep()` inside a design that
assumed concurrent job execution wouldn't be blocked by one slow gatekeeper wait — that
assumption doesn't hold in `BlockingScheduler` with `max_instances=1` per job.
**How to avoid:** Use a small, independent `max_wait` for the *admission-control* wait inside
the gatekeeper (order of 1-2s), decoupled from `retry_after_seconds` (which can stay as
documentation/config for a human tuning rate limits, but shouldn't drive the sleep duration).
**Warning signs:** Bot goes quiet for tens of seconds under any load; APScheduler logs show
missed job executions (`EVENT_JOB_MISSED`).

### Pitfall 2: Revoking anon grants before confirming service_role is live everywhere
**What goes wrong:** Shipping the RLS-revert migration before `SUPABASE_KEY=service_role` is
confirmed set in *both* Railway and local `.env` reproduces the exact "app has had no way to
reach the database at all" outage `20260825000001`'s header already documents happening once.
**Why it happens:** Migrations and env-var changes are deployed independently (Railway env var
change vs. `supabase db push`), and it's easy to run the migration first because it's "just a
grant."
**How to avoid:** Follow the 3-step sequence in the Service Role section above — env change,
verify, only then migrate.
**Warning signs:** `/health` returns `{"ok": false}` (its `ping()` call hits `run_query`); any
webhook processing starts failing with permission-denied errors from Postgres.

### Pitfall 3: Direct-connection `DATABASE_URL` silently failing on Railway
**What goes wrong:** Using the `db.<ref>.supabase.co:5432` direct-connection string (the one
that *looks* like the "normal"/simplest option in the Supabase dashboard) for `DATABASE_URL`
on Railway, where outbound IPv6 is off by default — DNS for that host is IPv6-only without
the (paid) IPv4 add-on, so the worker falls back to `MemoryJobStore` not because
`DATABASE_URL` is unset, but because every connection attempt fails and is presumably caught
somewhere/retried, or the worker crashes on boot.
**Why it happens:** Supabase's dashboard shows the direct-connection string most prominently;
it's not obvious it requires IPv6 support from the hosting platform.
**How to avoid:** Use the Session Pooler string (`aws-<region>.pooler.supabase.com:5432`,
username `postgres.<project-ref>`) for `DATABASE_URL`.
**Warning signs:** Worker logs show `"Using SQLAlchemyJobStore"` but the process still crashes
or hangs on startup; connection timeouts referencing an IPv6-looking address.

### Pitfall 4: `postgres://` scheme in a hand-typed/copied `DATABASE_URL`
**What goes wrong:** SQLAlchemy 1.4+/2.0 raises `NoSuchModuleError` if `DATABASE_URL` starts
with `postgres://` instead of `postgresql://`.
**Why it happens:** Older tutorials, Heroku-style docs, and some tools emit the short form.
**How to avoid:** Copy the connection string verbatim from the Supabase dashboard (which
already uses `postgresql://`); don't hand-construct it from separate host/port/user fields.
**Warning signs:** Worker crashes immediately on boot with `NoSuchModuleError` when
`SQLAlchemyJobStore(url=...)` is constructed.

## Sources

### Primary (HIGH confidence — direct repo/environment verification)
- `app/services/processor.py`, `app/services/retry_queue.py`, `app/services/retry_actions.py`,
  `app/services/followup.py`, `app/services/monthly_report.py`, `app/routers/ui_api.py`,
  `app/services/pdf_invoice.py`, `app/services/whatsapp_meta.py`, `app/db/database.py`,
  `app/shared/gatekeeper.py`, `app/worker.py`, `app/main.py`, `app/services/config.py`,
  `app/services/ai_service.py` — read directly, call sites and behavior confirmed by reading
  actual code, not inferred.
- `supabase/migrations/20260614000000_baseline.sql`, `20260614000001_durable_messaging.sql`,
  `20260614000003_security_rls.sql`, `20260825000001_fix_rpc_grants.sql` — read directly for
  schema and RLS/grant history.
- `tests/conftest.py`, `tests/unit/test_gatekeeper.py`, `tests/unit/test_retry.py`,
  `tests/unit/test_retry_actions_pdf.py`, `tests/unit/test_followup.py`,
  `tests/unit/test_monthly_report.py`, `tests/integration/test_orders_api.py` — read directly
  for current test-mocking patterns.
- `docs/BACKUP_DRILL.md`, `config/rate_limits.json`, `Procfile`, `supabase/config.toml` — read
  directly.
- Direct command execution in this environment: `docker --version` (not found),
  `npx supabase db push --dry-run --linked`, `npx supabase db dump --dry-run --linked`,
  `npx supabase db push --help`, `npx supabase link --help`, `npx supabase db dump --help`
  (CLI v2.115.0) — all run and observed directly, not inferred from documentation.

### Secondary (MEDIUM confidence — official docs, cross-checked but not directly tested
against this project's live Supabase/Railway instances)
- [Supabase: Connect to your database](https://supabase.com/docs/guides/database/connecting-to-postgres) — direct/session-pooler/transaction-pooler connection types, ports, IPv4/IPv6 support.
- [Supabase: Using SQLAlchemy with Supabase](https://supabase.com/docs/guides/troubleshooting/using-sqlalchemy-with-supabase-FUqebT) — pooling recommendations, `NullPool` note for transaction mode.
- [Supabase CLI: db push reference](https://supabase.com/docs/reference/cli/supabase-db-push) — flags, migration-history-table behavior (cross-verified directly against installed CLI's own `--help` and `--dry-run` behavior).
- [Supabase CLI: db dump reference](https://supabase.com/docs/reference/cli/supabase-db-dump) — flags (cross-verified against installed CLI's `--help`).
- [Supabase: Database migrations guide](https://supabase.com/docs/guides/deployment/database-migrations) — `supabase_migrations.schema_migrations` tracking table, "never change the remote database directly" guidance.
- [Railway Docs: Outbound Networking](https://docs.railway.com/networking/outbound-networking) — IPv6 opt-in toggle, off by default.
- [Railway Changelog #0297 (2026-07-03)](https://railway.com/changelog/2026-07-03-the-peaceful-way-to-ship-software) — static outbound IPs / IPv6 CLI support, confirms IPv6 is a recent/opt-in feature.
- [APScheduler 3.x executors.pool docs](https://apscheduler.readthedocs.io/en/3.x/modules/executors/pool.html) and [APScheduler 3.x user guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — default `ThreadPoolExecutor(10)`, `max_instances`/`coalesce`/`misfire_grace_time` job defaults.
- [SQLAlchemy GitHub discussion #6423](https://github.com/sqlalchemy/sqlalchemy/discussions/6423) — `postgres://` scheme removal in 1.4+.
- Supabase service_role security guidance (multiple cross-checked sources: Supabase's own [Securing your data](https://supabase.com/docs/guides/database/secure-data) doc, plus community sources) — service_role bypasses RLS, server-side-only usage.

### Tertiary (LOW confidence — single-source or SEO-content blog posts, flagged, treat as
directional not authoritative)
- Blog posts on Supabase free-tier backup limitations (e.g. simplebackups.com,
  axonbuild.com, akashy.com — multiple independent sources agree Pro tier = daily backups,
  7-day retention, free tier = none, so raised to MEDIUM by cross-agreement, but none is an
  official Supabase pricing page fetched directly in this research pass — **recommend
  confirming this project's actual tier directly in the Supabase dashboard before the plan
  finalizes the backup cadence**).

## Metadata

**Confidence breakdown:**
- Outbox migration call-site inventory: HIGH — every call site read directly in this repo.
- Gatekeeper design: HIGH on the problem/call-sites (verified in repo), MEDIUM on the specific
  `max_wait` numeric recommendation (reasoned from the poll intervals, not externally
  benchmarked — the plan should treat 1-2s as a starting point, not a hard requirement).
- Service-role sequencing: HIGH — reasoned directly from the actual migration files and
  `database.py`'s actual code path, not from generic Supabase advice.
- APScheduler/Supabase pooler connection-string guidance: HIGH on the Supabase side (official
  docs, current), MEDIUM on the Railway-specific interaction (Railway's IPv6-default-off
  behavior is documented but not directly tested against this project's actual Railway
  service).
- Backup/restore CLI mechanics: HIGH — directly executed in this environment, overriding both
  stale project documentation and some inconsistent third-party commentary.
- Dead-letter dashboard UX: MEDIUM — recommendation is reasoned from the existing design
  system and route structure (verified), but the specific "5th tab" choice is a judgment call
  explicitly left to Claude's discretion by CONTEXT.md, not a research finding.

**Research date:** 2026-08-25
**Valid until:** Supabase CLI behavior and Railway networking defaults can change — re-verify
CLI Docker-independence and Railway IPv6 defaults if this research is used more than ~60 days
from this date. The in-repo call-site inventory (outbox, gatekeeper, migrations) stays valid
until the code itself changes.
