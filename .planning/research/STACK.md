# Technology Stack

**Project:** ALYASMEEN AuntOps Production Readiness  
**Researched:** 2026-06-14  
**Research scope:** Productionizing the existing Python/FastAPI, Supabase, Meta WhatsApp Cloud API, Anthropic, Jinja dashboard, and APScheduler system  
**Overall confidence:** HIGH for documented platform capabilities and package versions; MEDIUM where availability, pricing, or limits depend on the owner's live plans and accounts

## Recommendation Summary

Keep the existing layered modular monolith and its current providers. Production readiness does not require microservices, Kubernetes, Redis, Celery, a JavaScript dashboard rewrite, or a new database. The necessary changes are narrower:

1. Make Supabase the controlled system of record, replacing arbitrary SQL RPCs with migrations, normal table operations, and narrow transactional functions.
2. Deploy one FastAPI web process and one separately managed scheduler/worker process from the same immutable Railway image.
3. Treat Meta webhooks and outbound messages as durable, idempotent jobs rather than synchronous request work.
4. Keep the direct Anthropic SDK, but pin a model snapshot, validate every tool call, add release-gating evaluations, and fail to human handoff.
5. Replace the current dashboard password cookie with Supabase Auth MFA plus an opaque server-side application session.
6. Add GitHub Actions release gates, Sentry, structured logs, external uptime and job-heartbeat checks, independent encrypted backups, and exercised recovery procedures.

Migration-cost estimates use these bands:

| Cost | Expected effort |
|------|-----------------|
| Low | Less than 1 engineer-day |
| Medium | 1-3 engineer-days |
| High | 4-7 engineer-days, including tests and rollout |

## Version Selection Policy

- Keep Python on the 3.11 line for this milestone, but patch from 3.11.9 to **3.11.15**. Moving to Python 3.12 is lower priority than eliminating production blockers and should happen after launch qualification.
- Declare direct Python dependencies with a lower bound at the tested release and an upper bound before the next incompatible minor or major release.
- Commit `uv.lock` and deploy only with `uv sync --frozen --no-dev`. The lockfile, not broad `>=` entries in `requirements.txt`, defines the deployed environment.
- Pin deployment tools and GitHub Actions. Use immutable Docker image digests or commit-derived image tags, never `latest`.
- Apply routine dependency updates monthly through staging. Expedite security fixes after review rather than allowing unattended production upgrades.
- Pin external API versions and model snapshots explicitly. Maintain quarterly Meta Graph API and Anthropic model review tasks.

## Recommended Stack

### Core Runtime and Framework

| Technology | Version or rule | Purpose | Why | Confidence | Migration cost |
|------------|-----------------|---------|-----|------------|----------------|
| Python | 3.11.15, exact patch in image | Application runtime | Retains compatibility and minimizes one-month migration risk while moving off the older 3.11.9 security patch level. | HIGH | Low |
| FastAPI | `>=0.137,<0.138`, exact in `uv.lock` | HTTP application and dependency injection | Keeps the current framework and current production/deployment behavior. No framework rewrite is justified. | HIGH | Low |
| Uvicorn Standard | `>=0.49,<0.50`, exact in `uv.lock` | ASGI server | Direct Uvicorn is sufficient on Railway. Gunicorn and the retired prebuilt Uvicorn/Gunicorn image add no benefit at this scale. | HIGH | Low |
| Pydantic | `>=2.13,<3`, exact in `uv.lock` | Request, configuration, and tool validation | Already fundamental to FastAPI and suitable for strict provider payload and AI tool schemas. | HIGH | Low |
| pydantic-settings | Latest compatible 2.x, exact in `uv.lock` | Typed environment configuration | Replaces scattered `os.getenv` calls and unsafe production defaults with startup validation. | HIGH | Medium |
| Jinja2 | Keep current 3.1.x, exact in `uv.lock` | Server-rendered operator dashboard | The single-operator dashboard does not justify a SPA rewrite. Retain automatic escaping and add CSP-compatible templates. | HIGH | Low |

### Database and Data Access

| Technology | Version or rule | Purpose | Why | Confidence | Migration cost |
|------------|-----------------|---------|-----|------------|----------------|
| Hosted Supabase | Pro baseline; verify live plan | Managed PostgreSQL, Auth, API, backup console | Preserves the existing data layer and adds production backup visibility and Auth capabilities. Free-tier backup constraints are not adequate for production. | HIGH | Low |
| PostgreSQL | Supabase-managed current major | Transactional system of record | Orders, conversations, inbox, outbox, sessions, audits, and scheduler state need ACID transactions and uniqueness constraints. | HIGH | Medium |
| `supabase-py` | `>=2.31,<2.32`, exact in `uv.lock` | Application HTTPS access to Supabase | Keeps current integration. Use the async client, timeouts, table APIs, and narrow RPCs rather than arbitrary SQL strings. | HIGH | Medium |
| Supabase CLI | Pin the tested stable release in CI | Local database, migrations, lint, test, deploy | Provides reproducible migrations, `db reset`, `db lint`, dry runs, and controlled pushes. | HIGH | Medium |
| pgTAP | Supabase-supported release | Database function, constraint, and RLS tests | Critical transactional and access behavior belongs close to PostgreSQL and must be tested independently of Python mocks. | HIGH | Medium |
| PostgreSQL inbox/outbox tables | Schema migration, not a new service | Durable provider event and job queues | At current volume, PostgreSQL can safely provide idempotency, retries, scheduling, and `SKIP LOCKED` worker claims without Redis/Celery. | HIGH | High |

Use normal table operations for ordinary CRUD. For multi-row order creation, worker claims, inventory changes, and other atomic workflows, use named PostgreSQL functions with typed arguments and fixed SQL. Prefer `SECURITY INVOKER`. If a function genuinely needs `SECURITY DEFINER`, set `search_path = ''`, schema-qualify every object, revoke execution from public roles, and grant only the backend role.

The generic `run_query` and `run_exec` functions are a production blocker. They combine authorization risk, SQL-injection risk, weak schema contracts, and difficult migration testing. Remove them from all user-influenced paths and then revoke/drop them.

### Deployment and Process Management

| Technology | Version or rule | Purpose | Why | Confidence | Migration cost |
|------------|-----------------|---------|-----|------------|----------------|
| Railway | Current managed platform; two environments | Web and worker hosting | Retains the existing target and supplies builds, deployments, logs, metrics, health gating, and rollback actions. | HIGH | Medium |
| Docker | Checked-in multi-stage Dockerfile | Reproducible application image | Replaces implicit Nixpacks behavior with an auditable Python patch, locked dependencies, non-root user, and identical web/worker artifact. | HIGH | Medium |
| `uv` | 0.11.21, pinned in Docker and CI | Dependency resolution and installation | The repository already has `uv.lock`; frozen installs are fast and deterministic. | HIGH | Low |
| Railway pre-deploy command | Explicit per release | Release checks only | Suitable for a bounded compatibility check. Do not run application migrations automatically from every replica startup. | HIGH | Low |
| Railway restart policy | On failure, bounded retries | Process recovery | Handles process crashes while external monitoring detects persistent failure. | HIGH | Low |
| Railway cron | Only for standalone bounded commands | Backup launch or infrequent maintenance | Useful for UTC schedules of at least five minutes, but not a replacement for the persistent application worker or business job state. | HIGH | Low |

Deploy the same image as two Railway services:

```text
Meta / Browser
      |
      v
Railway Web: Uvicorn, 1 process, 1 replica
      |
      v
Supabase PostgreSQL: domain data + inbox + outbox + sessions + audits
      ^
      |
Railway Worker: APScheduler + durable inbox/outbox polling, 1 replica
```

Start with one Uvicorn worker and one web replica. This matches the current low traffic and avoids multiplying process-local caches. Scale web replicas only after all request work is idempotent and no required state is process-local. The scheduler must not be created from the FastAPI lifespan once multiple web processes or rolling deployments are possible.

Provide:

- `/health/live`: process is running; no external dependency call.
- `/health/ready`: required configuration is valid and a short Supabase probe succeeds.
- `/version`: commit SHA and release identifier, with no secrets.

Railway health checks gate deployment but are not continuous uptime monitoring. Use an external monitor as well.

### Meta WhatsApp Business Platform

| Technology | Version or rule | Purpose | Why | Confidence | Migration cost |
|------------|-----------------|---------|-----|------------|----------------|
| Meta WhatsApp Cloud API | Graph API `v25.0`, environment-pinned | Production messaging | `v25.0` was released February 18, 2026 and is the current documented Graph version found during research. Never use an unversioned or `latest` URL. | HIGH | Medium |
| `httpx` | `>=0.28.1,<0.29`, exact in `uv.lock` | Async Meta HTTP client | Replaces blocking `requests` in async request paths and provides explicit connect, read, write, pool, and total timeouts. | HIGH | Medium |
| PostgreSQL durable inbox/outbox | Project schema | Idempotency and delivery state | Meta retries failed webhooks for up to seven days and duplicates can occur. Persistence before processing is mandatory. | HIGH | High |
| Meta system-user token | Long-lived, secret-managed | Server authentication | Temporary dashboard tokens expire quickly and are not production credentials. | HIGH | Low |

Webhook handling must:

1. Read the raw body.
2. Verify `X-Hub-Signature-256` with HMAC-SHA256 using the Meta app secret and constant-time comparison.
3. Parse the actual nested WhatsApp envelope and validate supported event shapes.
4. Insert the event with a unique provider event/message identifier before business processing.
5. Return `200` for a durably accepted event or known duplicate.
6. Let the worker process events with bounded retries and a terminal dead-letter state.

Outbound messages must be committed to an outbox in the same transaction as the domain event that requested them. The worker sends them, records Meta response IDs and status webhooks, and classifies retryable failures. Do not blindly retry POST requests after an ambiguous network timeout because the first request may have succeeded.

Use approved utility templates outside the 24-hour customer service window. Maintain a template registry containing Meta name, language, category, variable contract, approval status, and last verification date. Follow-ups and promotional messaging require verified opt-in and current Meta policy review.

Do not change to a WhatsApp BSP solely for production hosting. Consider a BSP only if the owner's Meta onboarding, support, billing, or phone-number migration remains blocked after direct Cloud API setup.

### AI Reliability

| Technology | Version or rule | Purpose | Why | Confidence | Migration cost |
|------------|-----------------|---------|-----|------------|----------------|
| Anthropic Python SDK | `>=0.109,<0.110`, exact in `uv.lock` | Claude Messages API | Keeps the direct SDK and supplies async operation, typed errors, request IDs, timeouts, and bounded automatic retries. | HIGH | Medium |
| Claude Haiku 4.5 | Snapshot `claude-haiku-4-5-20251001` | Production conversation model | A fixed snapshot prevents silent behavior changes and is the current Haiku generation documented during research. | HIGH | Medium |
| Pydantic tool schemas | Current Pydantic 2.x | Validate model-proposed actions | The model may propose actions; deterministic application code remains the authority. | HIGH | Medium |
| Pytest evaluation harness | Pytest 9.1.x, versioned fixtures | Release-gating behavioral evaluation | A repository-owned fixture set is easier to audit and integrate into CI than adopting an orchestration framework. | HIGH | High |

Use one shared `AsyncAnthropic` client with explicit deadlines. Keep the SDK's transient retries low, such as two attempts, and respect `Retry-After`. Record the Anthropic request ID, model snapshot, prompt/tool-schema version, latency, token use, error class, and final outcome. Do not log full conversation content by default.

Every model-proposed action must pass:

- strict schema validation with unknown fields rejected;
- deterministic price, catalog, medical-safety, and authorization rules;
- an idempotency key;
- current database-state validation;
- an atomic transaction for state changes;
- human confirmation or handoff for high-impact actions.

The production fallback for timeout, overload, malformed output, uncertainty, or unsafe intent is a deterministic safe response and human handoff. Do not silently switch to a larger model for risky customer actions. Sonnet may be used offline as an evaluation aid, but not as an unreviewed production escalation path.

Maintain a versioned Arabic and English evaluation set covering noisy spelling, incomplete orders, unavailable products, duplicate messages, prompt injection, medical questions, price manipulation, cancellation, and handoff. Block release when agreed safety, task-success, latency, or cost thresholds regress.

Prompt caching is optional. Enable it only if telemetry shows a repeated stable prompt/tool prefix at or above the current model's cacheable-token minimum. It is not a substitute for reducing prompt size.

### Dashboard Security

| Technology | Version or rule | Purpose | Why | Confidence | Migration cost |
|------------|-----------------|---------|-----|------------|----------------|
| Supabase Auth | Email/password, public signup disabled | Operator identity | Replaces the current shared password and custom SHA256 authentication with managed credential storage and account recovery. | HIGH | High |
| Supabase Auth TOTP MFA | Require AAL2 before app session creation | Strong operator authentication | A single privileged dashboard account warrants phishing-resistant operational discipline and a second factor. | HIGH | Medium |
| Opaque server-side session | 256-bit random token; hashed token in PostgreSQL | Browser session | Supports immediate revocation, inactivity expiry, auditability, and no browser-readable bearer credential. | HIGH | Medium |
| Synchronizer CSRF token | Per app session | Unsafe form/API request protection | The server-rendered dashboard uses cookies, so state-changing requests require CSRF defense. | HIGH | Medium |
| Starlette security middleware | Version supplied by FastAPI | Host and transport hardening | `TrustedHostMiddleware`, HTTPS redirect where appropriate, and centralized headers fit the current stack. | HIGH | Low |

After successful Supabase Auth password and TOTP verification, create an application session row and set:

```text
__Host-auntops_session=<opaque token>; Secure; HttpOnly; SameSite=Strict; Path=/
```

Store only a keyed hash of the token. Use a 30-minute inactivity timeout, an 8-hour absolute timeout, rotation after login or privilege changes, and explicit logout/revocation. Keep an emergency recovery procedure and at least one tested administrative recovery path.

Centralize authentication and authorization in FastAPI dependencies. Protect every dashboard, JSON, broadcast, and mutation route. Do not mount development, debug, or mock-provider routes in production.

Add a restrictive Content Security Policy, HSTS after HTTPS/domain verification, `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, a strict referrer policy, and a minimal permissions policy. Preserve Jinja escaping, validate all input with Pydantic, and check `Origin`/`Referer` for unsafe same-origin requests in addition to CSRF tokens.

Do not use:

- the current `SHA256(secret:password)` cookie;
- a default production password or secret;
- JWTs or Supabase refresh tokens in browser storage;
- Starlette `SessionMiddleware` for confidential session data, because its cookie is signed rather than encrypted;
- process-memory-only login rate limiting;
- public Supabase signup.

### Observability and Operations

| Technology | Version or rule | Purpose | Why | Confidence | Migration cost |
|------------|-----------------|---------|-----|------------|----------------|
| `structlog` | `>=26.1,<27`, exact in `uv.lock` | JSON structured logs | Makes provider, order, job, and request context queryable in Railway logs without parsing prose. | HIGH | Medium |
| `asgi-correlation-id` | `>=5,<6`, exact in `uv.lock` | Request correlation | Propagates a stable request ID through FastAPI logs and error reports. | HIGH | Low |
| Sentry Python SDK | `sentry-sdk[fastapi]>=2.62,<3`, exact in `uv.lock` | Error and performance monitoring | Provides FastAPI exception capture and traces without operating another monitoring stack. | HIGH | Medium |
| Railway logs and metrics | Current platform capability | Runtime logs, CPU, memory, deployments | Already available and sufficient as the primary infrastructure view at current scale. | HIGH | Low |
| Better Stack Uptime | Current managed service | External HTTP checks and job heartbeats | Detects outages and missed scheduled jobs that Railway deployment health checks do not continuously monitor. | MEDIUM | Low |
| Supabase dashboard/advisors | Current platform capability | Database health, security, query and backup review | Native context is more actionable than duplicating all database telemetry initially. | HIGH | Low |

Set Sentry `send_default_pii=False`. Add a `before_send` scrubber for phone numbers, addresses, message bodies, cookies, authorization headers, provider tokens, and raw webhook payloads. Use sampling appropriate to low traffic, but capture all unhandled errors.

Structured events should include safe identifiers and timing:

- application request/correlation ID;
- release commit SHA;
- order, conversation, and job IDs;
- Meta `wamid`, status, and error code;
- Anthropic request ID, model snapshot, token counts, and error class;
- attempt number, queue age, duration, and terminal outcome.

Hash or truncate phone numbers. Never log access tokens, cookie values, full addresses, medical details, or full conversations.

Alert on:

- readiness failures and external downtime;
- webhook signature failures or sustained webhook 5xx responses;
- oldest unprocessed inbox age;
- outbox and retry backlog;
- terminal Meta delivery failures;
- Anthropic 429, 529, timeout, cost, or latency spikes;
- missing scheduler/worker heartbeat;
- repeated database or migration failures;
- backup failure or overdue restore drill;
- repeated dashboard login failures or MFA recovery events.

Do not self-host Elasticsearch, Prometheus, Grafana, or an OpenTelemetry collector for this milestone. Revisit OpenTelemetry when multiple services, higher throughput, or cross-provider trace analysis justify the operating cost.

### CI/CD and Supply Chain

| Technology | Version or rule | Purpose | Why | Confidence | Migration cost |
|------------|-----------------|---------|-----|------------|----------------|
| GitHub Actions | Actions pinned to commit SHAs | CI and controlled deployment | Native to the repository and supports checks, environments, approvals, and artifact provenance. | HIGH | High |
| Ruff | `>=0.15.17,<0.16`, exact in `uv.lock` | Formatting, lint, import and security rules | Fast single-tool baseline. Enable relevant `S` security rules with documented narrow ignores. | HIGH | Medium |
| Pytest | `>=9.1,<10`, exact in `uv.lock` | Unit, integration, provider-contract, and AI evaluation tests | Already aligned with the Python stack and suitable for release gates. | HIGH | High |
| pip-audit | `>=2.10,<3`, exact in `uv.lock` | Python vulnerability audit | Checks the locked dependency graph against published advisories. | HIGH | Low |
| Gitleaks | Pinned release/action | Secret scanning | Detects Meta, Supabase, Anthropic, and general credentials before merge. | HIGH | Low |
| Trivy | Pinned release/action | Container and OS package scan | Covers risks not visible to `pip-audit`. | HIGH | Low |
| Dependabot or Renovate | Weekly grouped PRs | Dependency and action updates | Makes updates reviewable and testable rather than silently mutable. | HIGH | Low |

Pull requests should run:

1. `uv sync --frozen`.
2. Ruff format check and lint.
3. Unit, security, provider-contract, and AI evaluation tests with an agreed coverage floor.
4. Local Supabase startup, `db reset`, `db lint`, pgTAP tests, and Python integration tests.
5. `pip-audit`.
6. Gitleaks.
7. Docker build, Trivy scan, and container smoke test.

Use separate staging and production Supabase, Railway, Meta, and Anthropic credentials. Pull-request jobs must not receive production secrets.

Deploy the exact tested commit to staging, run smoke tests, then require a GitHub production environment approval. Apply reviewed database migrations as a controlled release step before deploying code that requires them. Use expand/contract schema changes so the preceding image can still run during rollback.

Railway can wait for GitHub checks before autodeploying, but production should still be an explicit approved deployment. Railway rollback redeploys an older image with current environment variables, so configuration changes must remain backward-compatible or have their own rollback procedure.

### Backup and Recovery

| Technology | Version or rule | Purpose | Why | Confidence | Migration cost |
|------------|-----------------|---------|-----|------------|----------------|
| Supabase daily backups | Pro baseline; verify retention | Provider-managed database recovery | Provides an immediate managed recovery layer and backup visibility. | HIGH | Low |
| Supabase PITR | Target 7-day window if budget and compute tier permit | Low-RPO database recovery | Recommended for production if the owner accepts the additional compute and PITR cost. Availability and current pricing require account verification. | HIGH | Medium |
| `pg_dump` | Version compatible with Supabase PostgreSQL | Independent logical backup | Avoids depending exclusively on the same provider and project for recovery. | HIGH | Medium |
| `age` encryption | Pinned stable release | Encrypt logical dumps before upload | Backup files contain customer PII and must not exist as plaintext artifacts. | HIGH | Medium |
| AWS S3 | Separate account, versioning and lifecycle enabled | Off-provider backup storage | Mature, independent storage with durable retention controls. | HIGH | Medium |
| Restore drill | Quarterly and before major schema changes | Verify recoverability | A successful backup job does not prove the database, Auth dependencies, and application can be recovered. | HIGH | High |

Recommended recovery targets for the initial production scale:

| Data | RPO | RTO | Mechanism |
|------|-----|-----|-----------|
| Orders, conversations, inbox/outbox, sessions, audit | 6 hours without PITR; minutes with PITR | 4 hours | Supabase backup/PITR plus encrypted six-hour logical dump |
| Supabase Storage objects, if used | 24 hours | 8 hours | Separate object copy/versioned bucket; database backup contains metadata, not deleted object bytes |
| Application and migrations | Every commit | 1 hour | Git repository, immutable image, locked dependencies |
| Secrets and account recovery material | On change | 4 hours | Password manager/offline recovery record, never in repository backup |

Run a dedicated backup command every six hours, connect with a restricted backup credential where practical, create a logical dump, encrypt it locally with an offline-held public key, upload to S3, and emit a monitored heartbeat only after upload verification. Retain approximately 30 daily and 12 monthly recovery points, subject to the owner's legal and privacy policy.

Restore quarterly into an isolated temporary Supabase project. Verify schema migration state, row counts, key order/conversation workflows, inbox/outbox uniqueness, dashboard login recovery, and application startup. Record actual RPO/RTO and corrective actions.

Supabase database backups do not restore deleted Storage object bytes. If the application starts storing PDFs or media in Supabase Storage, add an independent object-copy procedure before relying on it for production records.

## Existing Libraries to Retain

Retain the current domain-focused libraries, locked to tested releases, unless tests reveal a concrete problem:

| Library/area | Decision | Rationale |
|--------------|----------|-----------|
| `python-bidi` and Arabic text handling | Retain | Existing Arabic output behavior is part of the product and unrelated to production topology. Add regression tests. |
| `fpdf2` | Retain | No PDF-engine migration is justified before production. Verify Arabic shaping, fonts, and deterministic output. |
| `python-multipart` | Retain if dashboard forms/uploads use it | Standard FastAPI form dependency. Enforce upload limits and content validation. |
| `python-dotenv` | Development only | Useful locally, but production configuration must come from Railway secrets and typed settings. |
| `requests` | Remove from async Meta/Anthropic paths | Blocking network calls can stall the event loop. Keep only if a clearly synchronous offline command still needs it. |
| APScheduler | Keep on latest stable 3.x, currently 3.11.2 | Version 4 remains a major behavioral migration. The production risk is process placement and durable effects, not a need to adopt an unreleased/new-major design. |

## Alternatives Considered

| Category | Recommended | Do not use now | Why not |
|----------|-------------|----------------|---------|
| Application shape | Modular monolith with separate web and worker processes | Microservices | Adds distributed transactions, deployment coordination, and observability cost without current scale pressure. |
| Hosting | Railway with Docker | Kubernetes or a self-managed VM | Operating burden is disproportionate to one operator and current volume. |
| ASGI process | Direct Uvicorn | Gunicorn or obsolete Uvicorn/Gunicorn base image | Railway supervises the process; one Uvicorn worker is initially sufficient. |
| Job queue | PostgreSQL inbox/outbox and one worker | Redis plus Celery | A second stateful system is unnecessary at 10-30 orders/day. |
| Scheduler | APScheduler 3.11.x in the worker | Scheduler embedded in every web process | Rolling deploys and horizontal scaling would create duplicate schedules. |
| Database access | Typed table operations and narrow RPCs | Generic arbitrary-SQL RPCs | Unsafe authorization boundary and weakly testable contracts. |
| Supabase key | Backend-only `sb_secret_...` where available | Browser-exposed secret/service-role key | Secret keys bypass RLS and belong only in trusted server environments. |
| AI integration | Direct Anthropic SDK and Pydantic | LangChain/LlamaIndex rewrite | Adds abstraction and migration risk without solving the actual reliability requirements. |
| AI model selection | Pinned Haiku 4.5 snapshot | Floating aliases or automatic high-cost fallback | Prevents silent behavior changes and uncontrolled risky escalation. |
| Dashboard | Jinja server rendering | React/Next.js rewrite | No production requirement justifies replacing a small operator interface. |
| Dashboard session | Opaque server-side session | Custom password hash cookie, JWT in local storage | Server-side sessions support revocation, inactivity limits, and safer browser storage. |
| Monitoring | Railway + Sentry + Better Stack | Self-hosted ELK/Prometheus/Grafana | Managed tools cover the current system with much lower operating cost. |
| Backups | Supabase plus encrypted off-provider dump | Supabase backups alone or GitHub artifacts | Independent recovery and longer controlled retention are required for customer data. |
| Delivery | Approved CI deployment | Direct production deploy on every push | Production needs migration checks, staging evidence, approval, and rollback readiness. |

## Installation

The exact command should update both `pyproject.toml` and `uv.lock`. These constraints are intentionally narrower than the repository's current broad lower bounds:

```powershell
# Runtime additions and production constraints
uv add "fastapi>=0.137,<0.138" "uvicorn[standard]>=0.49,<0.50"
uv add "pydantic>=2.13,<3" "pydantic-settings>=2,<3"
uv add "supabase>=2.31,<2.32" "anthropic>=0.109,<0.110"
uv add "apscheduler>=3.11.2,<4" "httpx>=0.28.1,<0.29"
uv add "structlog>=26.1,<27" "asgi-correlation-id>=5,<6"
uv add "sentry-sdk[fastapi]>=2.62,<3"

# Development and CI
uv add --dev "pytest>=9.1,<10" "ruff>=0.15.17,<0.16" "pip-audit>=2.10,<3"

# Verification
uv lock
uv sync --frozen
```

Pin non-Python tooling separately in Docker and GitHub Actions:

- `uv` 0.11.21
- the tested Supabase CLI release
- Gitleaks and Trivy releases
- every GitHub Action by full commit SHA
- `python:3.11.15-slim` by immutable image digest after validation

## Live Account Decisions to Verify

These cannot be proven from repository code and must be checked before production approval.

### Supabase

- Project is on Pro or higher and in the intended data region.
- Current project supports new publishable/secret keys; rotate from legacy keys when available.
- Backend secret is never present in dashboard HTML, browser JavaScript, logs, or public CI.
- RLS and grants are reviewed on every exposed table and function.
- Daily backup retention, latest successful backup, compute tier, PITR availability, and current PITR price meet the selected RPO.
- A separate staging project exists.
- Auth public signup is disabled; TOTP MFA, password policy, CAPTCHA/leaked-password protection, and custom SMTP availability match the plan.
- Database security and performance advisor findings are cleared or accepted.
- Connection choice for `pg_dump` works from Railway and uses TLS.

### Railway

- Staging and production environments use separate secrets and domains.
- Region, plan limits, custom-domain TLS, deployment timeout, restart policy, and log retention are acceptable.
- Web and worker are separate services using the same immutable image.
- Only one worker replica is permitted until queue and schedule concurrency are deliberately redesigned.
- Health-check path and timeout are configured, and external uptime monitoring is active.
- Production deployment credentials are restricted to the approved workflow.

### Meta WABA

- Meta business verification, app live mode, phone registration, display name, WABA ID, and phone-number ID are complete.
- The system-user token is long-lived, stored only as a secret, and has the minimum required WhatsApp permissions.
- The app is subscribed to the WABA `messages` webhook field.
- Webhook URL, verify token, app secret, and signature verification are tested against the real account.
- Required Arabic and English templates are approved with correct categories and variables.
- Quality rating, messaging limits, billing/payment method, opt-in evidence, and current policy status are acceptable.
- `v25.0` is available to the live app and a version-upgrade owner/calendar exists.

### Anthropic

- The workspace has access to `claude-haiku-4-5-20251001`.
- Rate tier, concurrency, spend limit, and billing alerts support pilot traffic.
- Production uses a dedicated workspace/API key with rotation and revocation procedures.
- Current commercial data-retention terms meet the project's 12-month conversation policy after application-side minimization.
- Any request for zero-data-retention or regional processing has been approved by Anthropic; do not assume eligibility.

### GitHub and Operations

- Branch protection requires CI and review for production code.
- GitHub Environments and required reviewers are available on the account plan.
- Actions minutes, Dependabot, secret scanning, and code-scanning availability are confirmed.
- Sentry and Better Stack region, retention, alert recipients, and PII settings are approved.
- The independent S3 bucket is in a separate account, has versioning/lifecycle controls, and its restore credential is recoverable.
- Named owners are assigned for WABA policy, database restore, secret rotation, incident response, and AI evaluation sign-off.

## Recommended Migration Order

1. **Lock and reproduce the runtime:** patch Python, narrow dependency constraints, update `uv.lock`, add typed settings, and create the Dockerfile.
2. **Secure and migrate data access:** establish Supabase CLI migrations, reconcile schema drift, add constraints/RLS/grants, replace generic SQL RPCs, and test restore.
3. **Make provider processing durable:** implement real Meta envelope/signature handling, inbox/outbox tables, idempotency, async `httpx`, and the separate worker.
4. **Harden AI behavior:** pin the model snapshot, add tool validation, deadlines, logging, deterministic fallback, and the evaluation release gate.
5. **Replace dashboard authentication:** Supabase Auth, TOTP, opaque sessions, CSRF, route authorization, rate limiting, and security headers.
6. **Add operational gates:** GitHub Actions, staging deployment, Sentry, structured logging, uptime/heartbeats, alerting, off-provider backups, and recovery exercises.
7. **Run the pilot:** verify live-account limits and policies, test rollback and restore, monitor real delivery statuses and handoffs, then approve broader traffic.

## Sources

Primary and official sources were preferred. Package versions were checked on June 14, 2026.

### Python, FastAPI, and Packaging

- Python 3.11 releases: https://www.python.org/downloads/
- FastAPI deployment concepts: https://fastapi.tiangolo.com/deployment/
- FastAPI Docker deployment: https://fastapi.tiangolo.com/deployment/docker/
- Uvicorn deployment settings: https://www.uvicorn.org/deployment/
- uv Docker integration: https://docs.astral.sh/uv/guides/integration/docker/
- FastAPI package release: https://pypi.org/project/fastapi/
- Uvicorn package release: https://pypi.org/project/uvicorn/
- uv package release: https://pypi.org/project/uv/

### Supabase

- Database backups and PITR: https://supabase.com/docs/guides/platform/backups
- API key types and secret-key behavior: https://supabase.com/docs/guides/api/api-keys
- Row Level Security: https://supabase.com/docs/guides/database/postgres/row-level-security
- PostgreSQL functions and security: https://supabase.com/docs/guides/database/functions
- Supabase CLI database migrations: https://supabase.com/docs/guides/deployment/database-migrations
- Database advisors: https://supabase.com/docs/guides/database/database-advisors
- SSL enforcement: https://supabase.com/docs/guides/platform/ssl-enforcement
- Auth MFA: https://supabase.com/docs/guides/auth/auth-mfa
- Auth sessions: https://supabase.com/docs/guides/auth/sessions
- Auth password security: https://supabase.com/docs/guides/auth/password-security
- Auth rate limits and SMTP considerations: https://supabase.com/docs/guides/auth/rate-limits
- Supabase Python package release: https://pypi.org/project/supabase/

### Railway

- Health checks: https://docs.railway.com/guides/healthchecks
- Dockerfiles: https://docs.railway.com/guides/dockerfiles
- Pre-deploy commands: https://docs.railway.com/deployments/pre-deploy-command
- Cron jobs: https://docs.railway.com/reference/cron-jobs
- Restart policy: https://docs.railway.com/reference/restart-policy
- GitHub autodeploy and waiting for CI: https://docs.railway.com/guides/github-autodeploys
- Deployment actions and rollback behavior: https://docs.railway.com/deployments/deployment-actions

### Meta WhatsApp

- Graph API versioning: https://developers.facebook.com/docs/graph-api/guides/versioning
- Graph API v25.0 changelog: https://developers.facebook.com/docs/graph-api/changelog/version25.0/
- Webhook signature verification: https://developers.facebook.com/docs/graph-api/webhooks/getting-started
- WhatsApp webhook retry and duplicate behavior: https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview/
- WhatsApp message service window: https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages
- WhatsApp Cloud API setup and tokens: https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
- WhatsApp pricing and message categories: https://developers.facebook.com/docs/whatsapp/pricing

### Anthropic

- Current Claude model overview and snapshot IDs: https://platform.claude.com/docs/en/about-claude/models/overview
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python
- API errors and request IDs: https://platform.claude.com/docs/en/api/errors
- Rate limits: https://platform.claude.com/docs/en/api/rate-limits
- Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Evaluation tool: https://platform.claude.com/docs/en/test-and-evaluate/eval-tool
- Developing tests and evaluations: https://platform.claude.com/docs/en/test-and-evaluate/develop-tests
- Commercial/API model-training policy: https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training
- Anthropic SDK package release: https://pypi.org/project/anthropic/

### CI/CD, Monitoring, and Security

- GitHub Actions security hardening: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
- GitHub deployment environments: https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment
- Dependabot configuration: https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file
- Sentry FastAPI integration: https://docs.sentry.io/platforms/python/integrations/fastapi/
- Sentry Python data collection controls: https://docs.sentry.io/platforms/python/data-management/data-collected/
- Better Stack cron and heartbeat monitoring: https://betterstack.com/docs/uptime/cron-and-heartbeat-monitor/
- APScheduler package release: https://pypi.org/project/APScheduler/
- HTTPX package release: https://pypi.org/project/httpx/
- structlog package release: https://pypi.org/project/structlog/
- Sentry SDK package release: https://pypi.org/project/sentry-sdk/
- asgi-correlation-id package release: https://pypi.org/project/asgi-correlation-id/
- Ruff package release: https://pypi.org/project/ruff/
- Pytest package release: https://pypi.org/project/pytest/
- pip-audit package release: https://pypi.org/project/pip-audit/
