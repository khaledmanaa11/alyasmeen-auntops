# Architecture Patterns

**Domain:** Production WhatsApp commerce agent
**Project:** ALYASMEEN AuntOps Production Readiness
**Researched:** 2026-06-14
**Overall confidence:** HIGH

## Recommended Architecture

Keep the modular monolith and Supabase. Do not introduce Redis, RabbitMQ, Celery, Kubernetes,
or microservices for 10-30 orders per day. The required production change is an operational
split inside the same codebase:

1. **Web process** - FastAPI ingress, dashboard pages, and authenticated JSON APIs.
2. **Worker process** - one process that claims durable work, calls Anthropic and Meta,
   generates invoices, sends retries, and owns recurring schedules.
3. **Supabase PostgreSQL** - system of record, transaction boundary, webhook inbox, durable
   outbox, audit history, handoff state, and worker leases.

Both processes should deploy from the same repository and image. This is still a modular
monolith; the split isolates request latency and scheduler ownership without adding a
distributed service architecture.

```text
                         TRUSTED OPERATOR
                    +-----------------------+
                    | Browser / Aunt        |
                    +-----------+-----------+
                                |
                         TLS + session + CSRF
                                |
PUBLIC INTERNET                  v
+-------------+        +-------------------------------+
| Meta        |------->| FastAPI web process           |
| Webhooks    | HMAC   |                               |
+-------------+        | - webhook ingress             |
                       | - dashboard/UI APIs            |
                       | - health/readiness             |
                       | - request auth/rate limits     |
                       +---------------+---------------+
                                       |
                         typed table access / narrow RPC
                                       |
                                       v
                       +-------------------------------+
                       | Supabase PostgreSQL           |
                       |                               |
                       | domain tables                 |
                       | webhook_events (inbox)        |
                       | outbox_jobs                    |
                       | handoffs / audit_log          |
                       | order_status_history          |
                       | worker_heartbeat / leases     |
                       +---------------+---------------+
                                       ^
                              claim / commit outcomes
                                       |
                       +---------------+---------------+
                       | Worker process                |
                       |                               |
                       | - event processor             |
                       | - policy gate                 |
                       | - AI adapter                  |
                       | - outbound dispatcher         |
                       | - recurring schedule owner    |
                       +---------+-------------+-------+
                                 |             |
                                 v             v
                            Anthropic API   Meta Send API
```

### Architectural Decision

Use a **durable inbox/outbox modular monolith**:

- The webhook request verifies and persists an event before returning success.
- Business effects and outbound messages are committed transactionally.
- A worker performs slow or failure-prone external calls.
- Every externally visible side effect has a stable idempotency key.
- The AI proposes actions; deterministic application policy authorizes them.
- The database, not process memory, records handoff, audit, retry, and ownership state.

This is the smallest architecture that addresses the current production risks. FastAPI
`BackgroundTasks` alone is not durable, and the current in-request AI/send flow can lose work
or cause duplicate orders when Meta retries.

## Trust Boundaries

| Boundary | Untrusted Input | Required Control |
|----------|-----------------|------------------|
| Meta to webhook | Raw HTTP body and headers | TLS, required `X-Hub-Signature-256` validation over raw bytes, envelope validation, payload size limit, idempotent persistence |
| Customer content to application | Text, button IDs, media metadata, profile names | Normalize and validate; never treat content as SQL, HTML, instructions, or trusted tool arguments |
| Application to AI | Conversation and catalog context | Data minimization, timeouts, spend limits, model/prompt version logging, deterministic fallback |
| AI to application tools | Model-generated tool name and arguments | Allowlist, schema validation, authorization, current-state checks, transaction boundary; model never receives DB or Meta credentials |
| Browser to dashboard | Cookies, forms, JSON requests | Strong login, secure session, CSRF, authorization, rate limiting, input validation, audit actor |
| App to Supabase | Elevated backend credential | Server-only secret, restricted function grants, RLS on exposed tables, no arbitrary SQL RPC |
| App to Meta send API | Destination, content, media | E.164 validation, template/window policy, response-code checking, timeout, durable retry, provider message ID capture |
| Deployment/operator | Secrets, migrations, feature flags | Separate environments, least access, MFA, reviewed migrations, release manifest, rollback runbook |

## Component Boundaries

| Component | Responsibility | Must Not Do | Communicates With |
|-----------|----------------|-------------|-------------------|
| `webhook_ingress` | Read raw body, verify HMAC, parse all batched entries/changes, persist events, return response | Call Claude, create orders, send WhatsApp replies | Meta, persistence gateway |
| `ui` and `ui_api` | Authenticate operator, validate requests, render state, call application services | Issue ad hoc SQL or send messages directly | Application services |
| `message_processor` | Claim one inbound event, preserve per-customer ordering, load state, run command/agent flow | Trust duplicate delivery or perform unrecorded side effects | Policy, agent, domain services |
| `policy_gate` | Pure deterministic decisions for autonomy, handoff, order-change eligibility, and prohibited actions | Generate customer prose or call providers | Message processor, order/handoff services |
| `agent_adapter` | Build prompts/tools, call Anthropic, validate response shape, return proposed action/reply | Mutate DB or call Meta directly | Anthropic, policy gate |
| `order_service` | Create/modify/cancel/transition orders atomically, enforce allowed state changes | Depend on UI or AI implementation | Typed repository/RPC, outbox |
| `handoff_service` | Open, acknowledge, resolve, and resume handoffs; pause automation | Infer resolution from model text | Policy, audit, outbox, UI |
| `outbox_dispatcher` | Claim due outbound work, call Meta/PDF handlers, record provider result, retry/dead-letter | Change business state outside a transaction | Supabase, Meta |
| `schedule_owner` | Materialize recurring due work with stable dedupe keys | Send directly or run in every web replica | APScheduler, outbox/jobs |
| `persistence_gateway` | Typed table operations and narrow transactional RPC calls | Accept caller-supplied SQL text | Supabase |
| `observability` | Correlation IDs, structured logs, metrics, error reporting, alerts | Log message bodies, addresses, tokens, or full phone numbers | All components |

The existing "one DB file" and "one AI file" conventions can remain, but their public
interfaces must become typed. `database.py` should expose repository methods such as
`ingest_webhook_event()`, `create_order()`, and `transition_order()`, not generic
`query(sql)` and `execute(sql)` to the rest of the application.

## Data Model Additions

Create these in M1 because M2-M4 depend on them:

| Table / State | Purpose | Key Constraints |
|---------------|---------|-----------------|
| `webhook_events` | Durable inbox for inbound messages and status callbacks | Unique `(provider, event_key)`; status, attempts, lease owner/expiry, next attempt, last error, received/processed timestamps |
| `outbox_jobs` | Durable outbound messages, invoices, alerts, reports, and follow-ups | Unique `dedupe_key`; kind, payload, status, attempts, lease, next attempt, provider message ID |
| `handoffs` | Operator work item and human-control state | One open handoff per conversation/customer; reason code, risk, source event, summary, status, resolution, timestamps |
| `order_status_history` | Explicit order transition history | Old/new status, actor, source event/request, timestamp |
| `audit_log` | Append-only security and business audit | Actor, action, entity, redacted before/after, request/event ID, release/policy version |
| `worker_heartbeats` | Operational evidence that durable work is being consumed | Worker role, release, last heartbeat, queue age |

Extend existing state:

- `sessions` or a new `conversations` record needs `automation_mode`:
  `auto`, `paused_handoff`, `manual_only`, `resuming`.
- Orders need an optimistic concurrency field such as `version`, plus cancellation metadata.
- `chat_history` needs a conversation/handoff link and retention/anonymization status.
- Provider message IDs and source event IDs must be carried through order, audit, and outbox
  records where relevant.

Raw webhook payloads should have a shorter retention period than conversation/handoff
records. Retain only what is necessary for replay and incident diagnosis, then delete or
redact. The project requirement remains 12 months for conversations and handoffs before
anonymization; order/accounting retention is a separate policy.

## Core Data Flows

### 1. Inbound Meta Webhook

```text
POST /whatsapp/webhook
  -> read raw bytes
  -> require and verify HMAC signature
  -> validate supported object/entry/change shapes
  -> flatten every message/status event in the batch
  -> INSERT webhook_events ON CONFLICT DO NOTHING
  -> return 200 only after persistence succeeds
```

Rules:

- Return `403` for an invalid signature.
- Return `400` for a structurally invalid or unsupported request that should not be retried.
- Return `5xx` if the database is unavailable before durable persistence, allowing provider
  retry rather than falsely acknowledging lost work.
- Return `200` for duplicates and successfully persisted events.
- Do not use the current global exception behavior that returns `200` for every webhook
  exception; that converts data loss into apparent success.
- Do not wait for Claude, order writes, invoice generation, or outbound Meta calls.

For inbound messages, use Meta's message ID as the primary event key. For status callbacks,
include message ID, status, and provider timestamp in the key or store transitions with a
unique constraint. Webhook idempotency is necessary but insufficient: each business action
must also use a source event/action key so a crash after commit cannot create a second order.

### 2. Message Processing

```text
worker claims pending webhook event
  -> serialize work per customer/conversation
  -> load automation mode and current session/order state
  -> if paused_handoff: record message; do not run AI
  -> deterministic command/risk classification
  -> optional Claude call for low-risk conversational handling
  -> validate proposed tool action through policy gate
  -> atomically commit domain mutation + audit + outbox
  -> mark event processed
```

At current volume, one worker naturally serializes most work. The claim function should
still be safe for future multiple workers using `FOR UPDATE SKIP LOCKED`, leases, or a narrow
RPC with equivalent semantics. Rapid messages from the same phone must not update the cart
concurrently or process out of order.

### 3. Order Creation and Change

Order confirmation currently performs separate writes for the order, generated name, and
each order line. A failure can leave a partial order. Replace this with one typed transactional
RPC:

```text
create_order(source_event_id, phone, fulfillment, address, requested_items)
  -> reject duplicate source_event_id
  -> load active products and authoritative prices
  -> validate quantities and fulfillment
  -> insert order and all lines
  -> append order history and audit
  -> enqueue customer confirmation and aunt alert
  -> clear cart/session
  -> commit once
```

Automatic modify/cancel must use a database-enforced compare-and-set:

```sql
UPDATE orders
SET status = 'cancelled', version = version + 1, updated_at = now()
WHERE id = :id AND phone = :phone AND status = 'to_do' AND version = :expected_version;
```

Zero affected rows means handoff or conflict. The AI prompt saying "only `to_do`" is not a
control; the transaction predicate is the control.

### 4. Outbound Effects

Order/status/handoff transactions write `outbox_jobs`; they do not call Meta inline.

```text
worker claims outbox job
  -> validate payload and policy
  -> call provider with timeout
  -> treat only successful HTTP response as success
  -> capture provider message ID
  -> mark sent, or schedule exponential retry
  -> after max attempts: dead-letter + alert + visible UI item
```

The current Meta sender returns non-2xx responses as ordinary dictionaries, so callers can
mark failed sends as successful. The provider adapter must raise or return a typed failure
for non-2xx responses.

### 5. Human Handoff

Opening a handoff is an atomic state transition:

```text
risk/uncertainty detected
  -> set automation_mode = paused_handoff
  -> create open handoff with reason and source event
  -> append audit decision
  -> enqueue customer acknowledgement
  -> enqueue aunt alert
```

While paused:

- Store all inbound messages and attach them to the open handoff.
- Do not call Claude or send normal automated replies.
- Optionally send one throttled reminder that a person will respond.
- Show queue age and unread activity to the aunt.

Resolution requires an explicit operator action with resolution category, notes/outcome, and
whether automation should resume. Store model name, prompt/policy version, trigger reason,
tool proposals and denials, and message IDs. Do not store hidden model reasoning or request
chain-of-thought.

## Persistence Pattern

### Use Typed PostgREST Operations Plus Narrow RPC

Use the Supabase client table API for simple CRUD and narrowly scoped RPC functions for:

- atomic order creation;
- conditional order changes/status transitions;
- webhook event ingestion;
- work claiming and lease renewal;
- handoff open/resolve transactions;
- retention/anonymization batches.

RPC functions should:

- accept typed business parameters, never raw SQL text;
- default to `security invoker`;
- set an explicit `search_path`;
- have `EXECUTE` revoked from `public`, `anon`, and `authenticated`;
- be granted only to the backend role that requires them;
- include stable idempotency and authorization checks;
- be versioned in migrations and covered by database tests.

### When Current Custom SQL RPC Is Unsafe

The existing `run_query(sql text)` / `run_exec(sql text)` design is already unsafe for
production if any of the following is true:

- callable with the documented anon key;
- executable by `public`, `anon`, or `authenticated`;
- implemented as `security definer`, especially in an exposed schema;
- missing a fixed `search_path`;
- capable of arbitrary DDL/DML supplied as text;
- used for multi-write business operations without a single transaction;
- dependent on client-side string escaping for user data.

The repo does not contain the deployed definitions or grants, so M1 must inspect the real
Supabase project before assuming they are safe. Even if grants are currently restricted,
arbitrary SQL-over-RPC has an unnecessarily large blast radius and should be replaced.

Supabase's current key guidance favors backend-only secret keys; legacy `anon` and
`service_role` JWT keys are scheduled for deprecation by the end of 2026. Use a production
backend secret only in Railway, never in the browser, and rotate it independently from
development.

## Scheduler Ownership

### Recommended

Run APScheduler only in the dedicated worker process, with one configured worker replica.
Schedules remain code-defined; durable job effects remain in PostgreSQL.

- APScheduler wakes up and inserts due jobs with deterministic keys such as
  `monthly_report:2026-06` or `followup:<order_id>`.
- The outbox/job claim transaction prevents duplicate execution.
- Worker startup performs a catch-up query for overdue work.
- A heartbeat and oldest-job-age alert detects a stopped worker.
- Web deployments and web scaling do not create more schedulers.

APScheduler's own documentation says a job store cannot safely be shared by multiple
scheduler processes because duplicate or missed execution can result. Do not try to solve
multi-process ownership by pointing all web workers at the same APScheduler job store.

### When In-Process Scheduling Becomes Unsafe

Treat scheduler-in-FastAPI as unsafe when any one condition is true:

- more than one uvicorn worker or Railway replica exists;
- zero-downtime deployments overlap old and new processes;
- web and scheduled work need independent restart or scaling;
- a missed job cannot be reconstructed from database state;
- a job performs a non-idempotent external side effect;
- the host can sleep or stop the web process;
- scheduled work materially affects webhook latency.

Railway keeps the old deployment active until the new healthcheck returns `200`, so
deployment overlap alone is enough to reject the current "scheduler starts in every FastAPI
process" design for production. A temporary single-process fallback is acceptable only with
a database advisory lease, idempotent job keys, one web replica, and an explicit no-scaling
constraint. The dedicated worker is the preferred M2 outcome.

## Observability

### Correlation

Generate or propagate these identifiers:

- HTTP `request_id`;
- Meta `event_id` / message ID;
- `conversation_id` and masked customer reference;
- `order_id`, `handoff_id`, `job_id`;
- `release_sha`, migration version, model and policy version.

The same identifiers must appear in structured logs, audit rows, error reports, and outbox
records.

### Logging

Emit JSON to stdout/stderr so Railway can index custom attributes. Never log:

- raw access tokens or API keys;
- full phone numbers;
- addresses;
- complete message bodies;
- full webhook payloads in normal operation.

Log event type, result, duration, retry count, provider status/error code, and stable masked
identifiers. Store sensitive diagnostic payloads only in access-controlled database rows
with retention.

### Metrics and Alerts

Railway supplies CPU, memory, disk, and network metrics, but not application latency,
error rates, or business KPIs. Add application telemetry for:

| Signal | Alert Condition |
|--------|-----------------|
| Webhook invalid signatures | Any sustained increase |
| Webhook persistence failures | Any production occurrence |
| Duplicate webhook rate | Spike above normal |
| Oldest unprocessed event age | More than 2 minutes |
| Oldest outbox job age | More than 5 minutes for customer replies |
| Dead-letter jobs | Any |
| Worker heartbeat | Missing for more than 2 minutes |
| Meta send failure rate | Sustained non-2xx or authentication error |
| Anthropic latency/error/rate limit | Budget breach or repeated fallback |
| AI cost/tokens | Daily and monthly budget thresholds |
| Open handoff age | Operator SLA breach |
| Database RPC latency/error | Sustained degradation |
| Backup age / restore drill | Backup missing or drill overdue |

Use an error tracker for stack traces and an external uptime check. Railway deployment
healthchecks are not continuous monitoring.

### Health Endpoints

- `/livez`: process event loop is alive; no external dependency calls.
- `/readyz`: production config valid, expected migration version present, short database
  query succeeds, and process role is ready.
- `/health/details`: authenticated operational detail only.

Do not fail web readiness because Anthropic or Meta is temporarily down. The web process can
still accept durable events while those dependencies recover. Expose worker health through
the heartbeat table and alerting, not a public worker HTTP server unless Railway requires it.

## Secrets and Configuration

- Fail startup in production when secrets are absent or insecure defaults remain.
- Replace `USE_MOCK_WHATSAPP=1` default with explicit environment selection and a production
  startup assertion that mock and debug routes are disabled.
- Keep development, staging/pilot, and production Supabase/Meta/Anthropic credentials
  separate.
- Store secrets only in Railway/Supabase secret facilities; never in `.env.example`, logs,
  URLs, source, database payloads, or audit JSON.
- Pin the Meta Graph API version in configuration, not source code, and add a review date for
  Meta's version lifecycle. The current hard-coded `v19.0` must be validated before M2
  production approval.
- Record non-secret configuration and feature flags in the release manifest.
- Provide kill switches for `AGENT_AUTONOMY`, outbound broadcasts, scheduled follow-ups,
  and all automatic customer replies. Handoff/manual mode must remain available.

## Migrations, Backups, Deployment, and Rollback

### Migrations

Use Supabase CLI migrations in `supabase/migrations/`; stop editing production schema in the
Dashboard. Establish a baseline from the actual remote project, then make every change
through versioned migration files.

Deployment sequence:

```text
test migration on clean local database
  -> test upgrade from production-like snapshot
  -> apply backward-compatible expand migration once
  -> deploy web/worker code
  -> verify health and smoke tests
  -> backfill asynchronously if needed
  -> contract/remove old schema only in a later release
```

Railway pre-deploy commands can run migrations and block deployment on failure, but with two
services the migration must run exactly once. Prefer a dedicated CI/release migration step,
or only the web service's pre-deploy command with explicit ownership. Do not let both web and
worker independently run `supabase db push`.

### Backups

Supabase currently provides automatic daily backups for Pro, Team, and Enterprise projects;
free projects are expected to make their own off-site dumps. For production:

- define and approve RPO/RTO before launch; recommended starting target is RPO <= 4 hours and
  RTO <= 4 hours;
- upgrade to at least Pro for managed daily backups, or automate encrypted off-site
  `supabase db dump` exports if remaining on free;
- add more frequent small logical exports if a 24-hour RPO is unacceptable;
- test restore to a separate project and run application smoke tests against it;
- record backup age and restore evidence;
- do not treat a backup as a substitute for migration rollback.

PITR is not justified at this load unless the business requires near-zero data loss and
accepts the additional Supabase compute/add-on cost.

### Rollback

Railway can roll back to a previously successful deployment, restoring its image and custom
variables. The application must make that safe:

- migrations use expand/contract compatibility;
- old code remains compatible with the expanded schema;
- destructive schema changes wait at least one release;
- release metadata records Git SHA, migration set, config version, prompt/policy version,
  and Meta API version;
- rollback drill covers both web and worker;
- database rollback normally uses a forward corrective migration, not blind reverse SQL.

## Failure Isolation

| Failure | Expected Behavior | Recovery |
|---------|-------------------|----------|
| Supabase unavailable before webhook persistence | Return `5xx`; no false acknowledgment | Meta retries; alert immediately |
| Supabase unavailable after event persisted | Web returns `200`; worker retries later | Queue age alert |
| Anthropic timeout/rate limit | No unsafe tool execution; deterministic fallback or handoff | Retry only where conversation semantics allow |
| Meta send API failure | Business transaction stays committed; outbox remains pending | Backoff, retry, dead-letter, operator visibility |
| Worker crash | Web still accepts events; no work lost | Railway restart plus stale-lease recovery |
| Web crash | Worker continues queued work | Railway restart/rollback |
| Dashboard unavailable | Bot and worker continue | Operator uses runbook; restore web |
| Duplicate webhook | Unique insert returns existing result | Respond `200`; no duplicate business action |
| Crash after order commit | Source idempotency returns existing order | Resume outbox delivery |
| Out-of-order provider status | Append status event; enforce monotonic/valid transition | Ignore stale state mutation, preserve audit |
| Bad AI proposal | Policy denial and handoff/fallback | Evaluation case added before next release |
| Backup/restore failure | Go-live blocked | Correct process and repeat drill |

## Patterns to Follow

### Pattern 1: Transactional Inbox/Outbox

**What:** Persist inbound work before acknowledgment and persist outbound effects in the same
transaction as business state.

**When:** Every webhook, order mutation, status transition, handoff, invoice, and alert.

**Example:**

```python
async def receive_meta_webhook(request: Request) -> Response:
    raw = await request.body()
    verify_meta_signature(raw, request.headers)
    events = parse_meta_envelope(raw)
    for event in events:
        persistence.ingest_webhook_event(event)  # unique provider event key
    return Response(status_code=200)
```

### Pattern 2: Deterministic Policy Around Probabilistic AI

**What:** Claude may interpret and propose; application code decides whether an action is
allowed against current database state.

**When:** All tool calls, order changes, risky topics, and customer commitments.

**Example:**

```python
decision = policy.authorize(
    proposed_action=agent_action,
    order=current_order,
    conversation=conversation,
)
if decision.requires_handoff:
    handoffs.open(decision.reason, source_event_id)
elif decision.allowed:
    domain.execute(decision.validated_action, source_event_id)
```

### Pattern 3: State Transitions as Services

**What:** UI, hard commands, agent tools, and retries call the same order/handoff transition
service.

**When:** Any mutation that has validation, audit, or notifications.

This prevents UI and bot paths from developing different business rules.

### Pattern 4: Idempotent Side Effects

**What:** Each effect has a stable key derived from the business event.

**Examples:**

- `order-confirmation:<order_id>`
- `order-status:<order_id>:<new_status>:<version>`
- `handoff-opened:<handoff_id>`
- `invoice:<order_id>:<invoice_version>`
- `monthly-report:<year>-<month>`

## Anti-Patterns to Avoid

### HTTP Handler as Workflow Engine

**What:** The current webhook performs DB reads/writes, Claude calls, order creation, and Meta
sends before responding.

**Why bad:** Provider retries and process failures can duplicate or lose effects; latency is
unbounded.

**Instead:** Verify, persist, acknowledge, then process in the worker.

### Returning 200 on Unpersisted Failure

**What:** The global webhook exception handler always returns `200`.

**Why bad:** Meta stops retrying while the event has been lost.

**Instead:** Return success only after durable ingest or confirmed duplicate.

### Direct Provider Calls from Domain/UI Code

**What:** Order status handlers send WhatsApp/PDF before or around status writes.

**Why bad:** State and communication diverge, errors are silently swallowed, and retries are
incomplete.

**Instead:** Domain transaction plus outbox.

### AI as Authorization Layer

**What:** Prompt rules are treated as sufficient protection.

**Why bad:** Prompt injection, ambiguity, and model variance can bypass prose instructions.

**Instead:** Deterministic policy and database constraints.

### Scheduler Per Web Process

**What:** APScheduler starts during every FastAPI startup.

**Why bad:** Multi-worker/replica and deployment overlap cause duplicate or missed jobs.

**Instead:** Dedicated schedule owner plus durable idempotent jobs.

### Generic SQL RPC

**What:** Send arbitrary SQL strings through PostgREST RPC.

**Why bad:** Excessive privilege, poor auditability, client-side escaping, and no domain
transaction boundary.

**Instead:** Typed table operations and narrow functions.

## Build Order and Milestone Dependencies

The five milestones are useful ownership labels, but they cannot be isolated. The dependency
graph is:

```text
Meta onboarding lane -----------------------------------------------> Go-live

M1 Supabase
  migrations + constraints + typed RPC
  inbox/outbox + audit/handoff/order-history schema
  backup/restore + retention
          |
          v
M2 FastAPI
  secure ingest + durable worker + provider adapters
  health/observability + CI/deploy/rollback
          |
          v
M3 Agent
  deterministic policy + handoff behavior + evaluated tools
          |
          v
M4 UI
  secure operator workflows over existing services/state
          |
          v
M5 Go-live
  integration proof, drills, pilot, cutover
```

### M1: Supabase to Production

Build in this order:

1. Inventory actual remote schema, function definitions, grants, RLS, indexes, and drift.
2. Establish Supabase CLI baseline migrations and clean-database reset.
3. Add constraints and indexes, including valid order statuses and unique idempotency keys.
4. Replace arbitrary SQL RPC with typed table operations and narrow transactional functions.
5. Add inbox, outbox, audit, handoff, order-history, lease, and heartbeat schema.
6. Make order creation and status transitions atomic.
7. Implement retention/anonymization operations.
8. Configure backups and complete a restore drill.

**Cross-cutting work that starts here:** correlation IDs in stored records, audit vocabulary,
release/migration metadata, production secret model, and Meta onboarding.

**Exit gate:** A clean database can be built from migrations; production-like data can be
restored; duplicate source events cannot create duplicate orders; no generic SQL RPC remains
production-callable.

### M2: FastAPI to Production

Build in this order:

1. Strict production config validation; disable debug/mock routes; migrate to FastAPI
   lifespan.
2. Raw-body Meta signature verification and full batched envelope parser.
3. Fast durable webhook ingest with explicit error semantics.
4. Worker process and durable event/outbox claim loops.
5. Typed Meta adapter with response validation, timeout, retries, and provider IDs.
6. Move status notifications, invoices, reports, and follow-ups to the outbox.
7. Add request IDs, structured logging, error tracking, application metrics, health/readiness,
   worker heartbeat, and alerts.
8. Add CI, one-owner migration deployment, Railway healthcheck, release metadata, and
   exercised rollback.

**Milestone isolation challenge:** minimum dashboard protection cannot wait for M4. Before an
M2 deployment is internet-accessible, either implement secure sessions/login rate limits/CSRF
for all mutating routes or keep the dashboard inaccessible behind an external access control.

**Exit gate:** A signed real-shaped webhook is durably acknowledged quickly; duplicates and
crash replay are safe; the web process can restart without losing work; exactly one scheduler
owner exists; deploy and rollback are demonstrated.

### M3: Agent to Production

Build in this order:

1. Define typed agent proposals and deterministic policy decisions.
2. Implement prohibited-action and risk/handoff rules before adding new autonomous tools.
3. Implement atomic handoff open/pause/resolution behavior over the M1 schema.
4. Route all agent tools through shared order/session/handoff services.
5. Add deterministic fallback for Anthropic outage, timeout, invalid tool arguments, and
   budget exhaustion.
6. Record model, prompt/policy version, latency, token/cost, proposed/allowed action, and
   outcome.
7. Run evaluation gates in shadow/manual mode before enabling autonomy.

Anthropic's current tool documentation notes that Haiku-class models may infer missing tool
parameters. Therefore tool schemas, application validation, and policy checks remain
mandatory even if strict tool-use features are adopted.

**Exit gate:** No model output can directly mutate data or send a message; risky categories
always create a durable handoff; eligible `to_do` changes are enforced transactionally;
evaluation, cost, and latency thresholds pass.

### M4: UI to Production

Build in this order:

1. Complete production authentication, secure sessions/cookies, CSRF, authorization, login
   abuse controls, and input validation.
2. Build the handoff inbox from M1/M3 state, including unread messages, age, reason, and
   acknowledge/resolve/resume actions.
3. Show audit history, order changes, failed/dead-letter outbound work, and worker/provider
   health in operator-friendly language.
4. Make every UI mutation call the same domain services/RPC used by bot/agent paths.
5. Add recovery actions that are explicit and audited; do not expose raw SQL or arbitrary
   retry action names.

**Milestone isolation challenge:** M4 owns the complete UX, but its data model and service
APIs must already exist in M1-M3. Do not postpone handoff/audit design until templates are
built.

**Exit gate:** The aunt can identify, acknowledge, resolve, and resume a handoff; see failed
communications; safely change orders; and understand who or what made each change.

### M5: Go-Live

M5 should add no foundational architecture. It validates the integrated system:

1. Complete WABA/number/domain/TLS configuration and validate the currently supported Meta
   Graph API version.
2. Run realistic end-to-end orders, eligible changes, prohibited changes, handoffs, status
   updates, invoices, retries, and provider callbacks.
3. Drill web rollback, worker rollback/restart, dead-letter recovery, and backup restore.
4. Verify alerts by inducing safe failures.
5. Train the aunt using production-like scenarios.
6. Pilot with selected customers under conservative feature flags.
7. Review queue age, handoffs, errors, cost, and operator feedback before public cutover.

**Exit gate:** Go/no-go evidence exists for every production definition in `PROJECT.md`; no
critical issue is deferred into public operation.

## Scalability Considerations

| Concern | Current load: 10-30 orders/day | Moderate growth | Large scale trigger |
|---------|-------------------------------|-----------------|---------------------|
| Web service | One web replica | Add replicas; ingress remains stateless | Separate public webhook and admin surfaces only if independent scaling/security requires it |
| Worker | One worker, sequential or small concurrency | Multiple claim workers with per-phone ordering | Dedicated queue infrastructure when DB polling/locks become a bottleneck |
| Scheduler | One dedicated owner, DB-deduped jobs | Same; workers may scale separately | Managed scheduler/event platform if schedule volume becomes material |
| Supabase access | HTTPS table API + narrow RPC | Tune indexes and claims | Consider direct pooled PostgreSQL only when measured latency/throughput justifies it |
| Inbox/outbox | PostgreSQL tables | Partition/archive if rows become large | External broker only after measured backlog or throughput pressure |
| AI | Per-message call with budget/fallback | Concurrency/rate-limit controls and caching | Separate inference orchestration only if cost/latency dominates |
| Observability | Structured logs, error tracker, small metric set | OpenTelemetry export and dashboards | Central telemetry pipeline with retention controls |

Do not preemptively change the architecture. Revisit the database-backed queue when sustained
work exceeds roughly several jobs per second, claim contention appears, queue tables become
operationally heavy, or independent worker scaling is repeatedly required. None of those
conditions are present now.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Modular monolith with web/worker roles | HIGH | Matches load and removes verified process-ownership risks |
| Supabase migration/key/RLS/function guidance | HIGH | Current official Supabase documentation |
| Durable inbox/outbox and transactional services | HIGH | Established reliability pattern directly addresses current non-atomic flows |
| Scheduler ownership | HIGH | APScheduler explicitly warns against multi-process shared scheduling |
| Railway deploy/health/rollback behavior | HIGH | Current official Railway docs, updated May 29, 2026 |
| Meta envelope/signature integration | MEDIUM | Official Meta samples confirm raw signature and batched processing; exact current payload/version matrix must be validated during M2 |
| Anthropic tool boundary | HIGH | Current official Claude tool and rate-limit documentation |
| Backup tier choice and RPO/RTO | MEDIUM | Platform behavior is verified; business tolerance and budget still require owner approval |

## Sources

### Supabase - HIGH confidence

- [Database migrations](https://supabase.com/docs/guides/deployment/database-migrations)
- [Database backups](https://supabase.com/docs/guides/platform/backups)
- [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Database functions and function privileges](https://supabase.com/docs/guides/database/functions)
- [Understanding API keys](https://supabase.com/docs/guides/getting-started/api-keys)

### FastAPI and APScheduler - HIGH confidence

- [FastAPI lifespan events](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [APScheduler FAQ: multi-process job stores](https://apscheduler.readthedocs.io/en/3.x/faq.html)

### Railway - HIGH confidence

- [Healthchecks](https://docs.railway.com/deployments/healthchecks)
- [Pre-deploy commands](https://docs.railway.com/deployments/pre-deploy-command)
- [Deployment rollback and actions](https://docs.railway.com/deployments/deployment-actions)
- [Restart policy](https://docs.railway.com/deployments/restart-policy)
- [Logs](https://docs.railway.com/observability/logs)
- [Metrics](https://docs.railway.com/observability/metrics)

### Meta and Anthropic

- [Meta WhatsApp Cloud API examples](https://github.com/fbsamples/whatsapp-api-examples) -
  official Meta sample repository, MEDIUM confidence for current-version details
- [Meta webhook signature validation sample](https://github.com/fbsamples/whatsapp-api-examples/tree/main/signature-validation-with-webhooks-payloads) -
  official sample, MEDIUM confidence
- [Claude tool definition guidance](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools) -
  HIGH confidence
- [Claude API rate limits](https://platform.claude.com/docs/en/api/rate-limits) -
  HIGH confidence
- [Claude API errors](https://platform.claude.com/docs/en/api/errors) -
  HIGH confidence
