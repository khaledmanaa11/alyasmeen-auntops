# Phase 6: Production Go-Live (M6) - Research

**Researched:** 2026-08-28
**Domain:** WhatsApp (Meta Cloud API) go-live cutover, staged pilot design, operator training, production readiness sign-off, for a single-operator FastAPI/Supabase modular monolith
**Confidence:** MEDIUM — HIGH for what exists in the repo (verified by direct code/test inspection); MEDIUM for live external state (Meta review status, product catalog, deployed env vars) which cannot be checked from this sandbox; MEDIUM for 2026 Meta policy specifics (WebSearch, cross-checked against official docs where possible)

**No CONTEXT.md exists for this phase** — `/gsd:discuss-phase 6` has not been run, so there are
no locked user decisions to reproduce here. Section "Open Questions" below is what that
discussion needs to resolve before planning can proceed.

---

## Summary

Phase 6 is not a build phase — almost everything it needs technically already exists in the
repo from Phases 1-5 (durable inbox/outbox, atomic orders, RLS + MFA dashboard, CSRF, policy
gate, five handoff triggers, audit trail, alerts page, eval gate, backup drill, structured
logging). What Phase 6 actually requires is **three things the repo cannot provide by itself**:
(1) the real Meta WABA number actually working end-to-end in production, which is blocked on
external Meta review state only the user can check; (2) a staged pilot run against real
customers, which is an operational exercise, not code; (3) an aunt-facing Arabic leave-behind
document, which does not exist yet — the dashboard itself is excellent (plain-Arabic action
cards, one-button resolve) but there is no static "what do I do when X" reference she can
consult without Khaled.

Two under-the-radar findings change the risk picture for criterion 1. First, **the codebase has
zero Meta message-template support** — every business-initiated message (the 3-day follow-up,
every aunt/admin WhatsApp alert, the monthly report) is a free-form `queue_text` call, and
Meta's 24-hour customer-service-window rule applies to *every* recipient of a business-initiated
message, not just "customers" — so once the number goes fully live, aunt/admin alerts sent
outside a 24h window from the recipient's last inbound message risk outright rejection
(Meta error 131047), not just delayed delivery. Second, `app/services/whatsapp_meta.py` still
hard-codes Graph API `v19.0` (2026-06-14 vintage), which was already flagged as stale in the
project's own pre-Phase-1 research and is now roughly two Graph API cycles behind current.
Neither of these are "fix before you can plan" blockers, but both belong in the plan.

The good news that materially de-risks planning: `REQ-nfr-test-coverage` (85%+ on core bot logic
+ API endpoints) is **already met today** — a live `pytest --cov=app --cov-report=term-missing`
run measured **85.40%** overall against the repo's own `fail_under = 85` gate in
`pyproject.toml`, which exists but is not wired into the default `pytest` invocation or into any
CI (there is no `.github/` directory in this repo at all). This mirrors exactly how
`docs/EVAL_GATE.md` treats the agent eval — a documented human pre-release step, not automation
— and Phase 6 planning should decide whether to keep that pattern (a `docs/COVERAGE_GATE.md`
alongside it) or invest in real CI for the first time.

**Primary recommendation:** Treat Phase 6 as three largely-independent tracks that can run in
parallel once Phase 5's `05-10` checkpoint is fully closed out live: (A) an external-facing Meta
go-live checklist (token, API version, template decision, business-review status — all
human-gated), (B) a written staged-pilot plan with explicit entry/exit criteria adapted from the
project's own pre-existing research, and (C) one Arabic one-page aunt cheat-sheet plus one
consolidated rollback/incident runbook for Khaled. None of these require new application code;
all of them require the user's input to plan, which is exactly what `/gsd:discuss-phase 6` needs
to gather next.

---

## Go-Live Readiness Inventory (against the 4 success criteria)

### Criterion 1 — "Real Meta WABA number is receiving and sending messages in production environment"

**What exists (verified in code):**
- Inbound webhook correctly parses the real nested Meta envelope
  (`entry[].changes[].value.messages[]`/`.statuses[]`), with defensive parsing that never
  crashes on an unexpected shape (source: app/routers/whatsapp.py:31-104). This directly
  supersedes the stale `.planning/codebase/CONCERNS.md` (dated 2026-06-13) finding #1, which
  claimed the webhook only accepted a flat dev payload — that finding is **resolved**, not
  current.
- HMAC `X-Hub-Signature-256` verification gates every inbound POST before any DB write
  (source: app/routers/whatsapp.py:40-42).
- Durable inbox with `wamid`-keyed idempotency (`ON CONFLICT (wamid) DO NOTHING`) — a replayed
  Meta event produces one row, not a duplicate (source: app/routers/whatsapp.py:92).
- The web process only persists and 200s; all processing (AI, cart, order creation, sends) runs
  in the separate worker process's `process_webhook_events` poll (source: app/worker.py:35,
  app/services/processor.py). This split is itself the cleanest available operational pause
  lever — see "Rollback story" below.
- Real outbound sender `app/services/whatsapp_meta.py` raises `WhatsAppSendError` on any
  non-2xx Meta response (2026-08-25 hardening, confirmed in STATE.md's Accomplishments list) —
  the old "silently swallows a failed send" defect PITFALLS.md Pitfall 4 and
  `.planning/codebase/CONCERNS.md` both flagged is **resolved**.
- `USE_MOCK_WHATSAPP` env var swaps the whole sender/verifier pair
  (source: app/routers/whatsapp.py:8-11) — the one binary switch available today.

**What's missing or unverified (needs the user, not more code archaeology):**
- **Meta business review status is unknown from this sandbox.** CLAUDE.md and STATE.md both say
  "submitted, pending" as of the last update — this can only be confirmed live in Meta Business
  Manager. Blocking for criterion 1 by definition.
- **`WA_META_TOKEN` still needs the new system-user permanent token** — STATE.md's Todos list
  this explicitly; a temporary/user token will expire and silently break sends after go-live
  looks successful in testing.
- **Zero Meta message-template support anywhere in the codebase**
  (`grep -rn "template" app/services/whatsapp_meta.py` returns nothing). Every
  business-initiated message — the 3-day post-delivery follow-up
  (source: app/services/followup.py:17-21,61), every new-order/permanent-failure/new-device
  alert to `AUNT_PHONE`/`ADMIN_PHONE` (source: app/services/handoff.py, app/services/processor.py
  `notify_permanent_failure`), and the monthly report (source: app/services/monthly_report.py:152)
  — goes out as free-form text via `processor.queue_text`. See "Common Pitfalls" below for why
  this is a real go-live risk, not a cosmetic one.
- **Graph API version hard-coded to `v19.0`** in 5 places in `whatsapp_meta.py` (lines 42, 76,
  111, 122, 166) — flagged as a risk in the project's own pre-existing research
  (`.planning/research/PITFALLS.md` Pitfall 19, `.planning/research/ARCHITECTURE.md`:423-425)
  before any of Phases 1-5 were built, and still true today. WebSearch (MEDIUM confidence,
  conflicting sources on the exact current number) suggests the current stable version is
  several cycles ahead (v21-v25 range as of 2026) — verify against
  https://developers.facebook.com/docs/graph-api/changelog before go-live, since Graph API
  versions are retired roughly two years after the next release ships.
- **Real product catalog and product images are unverified live state**, not a code gap —
  CLAUDE.md's "Still To Do" list items 2 and 5 (add real products via `/products`, add
  `image_url` column + real images) are still open per that doc; confirmed no `image_url` column
  exists in any migration (source: `supabase/migrations/*.sql`, `app/db/schema.sql:8`).
- **`app/data/knowledge/` is NOT empty**, contrary to CLAUDE.md's "Still To Do" item 6 and the
  wiki's `alyasmeen-auntops.md` page — 6 Arabic knowledge files already exist
  (`about_store.md`, `ingredients_faq.md`, `returns_policy.md`, `shipping_policy.md`,
  `skin_advice.md`, `store_info.md`, source: app/data/knowledge/). This is a **stale TODO**, not
  a real gap — worth correcting in CLAUDE.md/the wiki as part of this phase's documentation
  work, and worth re-running the eval gate's `informational` tier (currently capped by this gap
  per `docs/EVAL_GATE.md`'s "Known limitations") to see if the loose 15-point tolerance can
  tighten now that grounding content exists.

### Criterion 2 — "Staged pilot with selected customers completes with zero critical defects"

Nothing pilot-specific exists yet — no pilot cohort list, no daily reconciliation template, no
defined "critical defect" bar for this repo specifically. See "Staged Pilot Design" below for
what the project's own pre-existing research already specifies, and "Open Questions" for what
still needs a human decision.

### Criterion 3 — "Aunt demonstrates ability to operate all daily workflows independently using documentation"

**What exists:**
- The dashboard itself is already built for a non-technical Arabic-speaking operator: nav tabs
  in Arabic (طلبات/dashboard/منتجات/تنبيهات/محادثات/السجل/حسابي), plain-Arabic alert action
  cards with a WhatsApp-open button and hidden technical details
  (source: app/templates/alerts.html, 05-08), a bot-vs-aunt conflict modal, one-button handoff
  resolve (source: app/templates/handoffs.html, 05-07), and a readable audit trail with all 18
  operator actions mapped to Arabic sentences (source: app/templates/audit.html, 05-07).
- `docs/OPERATOR_ACCOUNTS.md` documents the account/MFA lifecycle (creation, assisted TOTP
  enrollment ritual, lost-phone recovery, password reset) — but it is written **for Khaled**, in
  English, as an admin runbook, not as something the aunt reads herself.
- `05-10-PLAN.md`'s Task 3 is a thorough one-time **assisted, verbal** walkthrough script
  (17 numbered steps, source: .planning/phases/05-operator-security-ux/05-10-PLAN.md:137-213)
  covering login/MFA, sessions, handoffs, audit, and alerts — but it is a live-verification
  checkpoint Khaled runs sitting with her, not a document she keeps.

**What's missing:**
- **No standalone Arabic-language leave-behind reference exists anywhere in the repo.** Every
  file under `docs/` is English and admin-facing (`BACKUP_DRILL.md`, `EVAL_GATE.md`,
  `OPERATOR_ACCOUNTS.md`). This is exactly the gap the project's own pre-existing pitfalls
  research called out before any code was written: "Create one-page Arabic-first runbooks for
  common incidents and escalation" (`.planning/research/PITFALLS.md` Pitfall 17). Criterion 3's
  own wording — "using documentation" — implies an artifact, not just a memory of a walkthrough.

### Criterion 4 — "Final production readiness check (monitoring, rollback, DR) is signed off"

**What exists:**
- `GET /health` — pings the DB, returns 503 if it fails (source: app/main.py:116-122). No
  `/livez`/`/readyz` split as the project's own pre-existing architecture research recommended
  (`.planning/research/ARCHITECTURE.md`:403-412) — a single endpoint conflates "process is up"
  with "DB is reachable," which is a real distinction for a Railway health-check gate but a
  minor one at this scale.
- `railway.json` pins the Nixpacks builder but sets **no `healthcheckPath`** — Railway's own
  deploy-gating health check is not explicitly wired to `/health` (source: railway.json).
- Internal monitoring is real but entirely in-app: `/alerts` dashboard (dead-lettered webhooks +
  permanently-failed outbox jobs, source: app/routers/ui_api.py `GET /api/alerts`), WhatsApp
  push alerts to the aunt (customer-facing failures) and admin (everything, including new-device
  logins) via `notify_permanent_failure`/handoff notifications, and structured JSON logging via
  `structlog` (source: app/shared/logging.py). **No external uptime checker, no error tracker
  (Sentry or equivalent), no business-KPI dashboard** — confirmed by
  `grep -rin "sentry|uptimerobot|datadog|prometheus" app/ docs/` returning nothing, even though
  the project's own pre-existing stack research explicitly recommended Sentry + an external
  uptime/heartbeat monitor before any of Phases 1-5 were planned
  (`.planning/research/STACK.md`:17,187,302). This is the single largest gap between what was
  originally scoped as "table stakes" and what actually shipped — worth an explicit go/no-go
  decision, not a silent gap (see Open Questions).
- Backup/restore: **already drilled live and passed**, RTO comfortably under the 4h target
  (source: docs/BACKUP_DRILL.md Drill Log, 2026-08-28 entry) — criterion 4's DR component is
  effectively satisfied already.
- Rollback: **no drill has ever been run**, and no consolidated rollback runbook exists in
  `docs/`. Railway's own image-rollback feature has never been exercised on this project
  (`.planning/research/PITFALLS.md`:307 flagged this before Phase 1 even started, and nothing in
  Phases 1-5 addressed it). See "Rollback story" below for what mechanisms actually exist today.
- No CI/CD pipeline exists at all — `REQ-prod-cicd` was satisfied narrowly by adding a
  `Procfile` defining Railway's `web`/`worker` roles
  (source: .planning/phases/02-application-hardening/02-02-SUMMARY.md:22), not by the
  "GitHub Actions with release approvals and rollback" the requirement's own detail text
  describes (source: .planning/REQUIREMENTS.md:80). Deploys are push-to-Railway with no test
  gate in between.

---

## Meta WABA go-live specifics (2026)

WebSearch-derived, cross-checked against official Meta for Developers pages where fetched
directly (marked HIGH); otherwise MEDIUM confidence from aggregator/blog sources with
overlapping claims.

### Business verification and messaging tiers (MEDIUM-HIGH)
- Tier ladder: 250 (starter, unverified) -> 2,000 -> 10,000 -> 100,000 -> unlimited. A portfolio
  without completed Meta Business Manager verification is capped at 250 messages/24h and cannot
  progress past it.
- To move past 250, either complete business verification (legal documents in Meta Business
  Manager, typically 2-5 business days) or send 2,000 delivered messages using high-quality
  templates.
- As of 2026, tier limits are **portfolio-based, not per-number** — every phone number in one
  Business Manager shares the portfolio's highest achieved tier, and a newly added number
  inherits that tier immediately (this is a change from the older per-number model, relevant if
  ALYASMEEN's number was originally provisioned under the old model).
- Meta re-evaluates tier eligibility roughly every 6 hours; advancing past 2,000 requires
  sustained high message quality plus using at least 50% of the current limit in a trailing 7-day
  window.
- At 10-30 orders/day this project will likely never need to progress past the 2,000 tier —
  worth confirming the account has at least completed business verification (the free unlock)
  rather than treating 250/day as a hard ceiling nobody checked.
- Source: https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits (official, fetched directly — HIGH)

### The 24-hour customer service window (HIGH)
- A user's inbound message/call opens a 24h window during which free-form (non-template)
  replies are allowed; any further inbound message resets the timer to 24h.
- Outside that window, a business-initiated message to that same recipient **requires an
  approved message template** — a free-form send is rejected, not silently converted.
- This rule is per-recipient, not per-"customer label" — it applies identically to a real
  shopper and to any other WhatsApp number the business number messages, including operational
  numbers like `AUNT_PHONE`/`ADMIN_PHONE` if they are ordinary WhatsApp users (which they are,
  in this architecture — see the Common Pitfalls entry below).
- **Pricing change effective 2026-10-01**: Meta will begin charging for service messages (free-
  form replies sent within the 24h window) and Utility-category templates, at the same rate as
  authentication messages — this window is free today but will not be after that date. Relevant
  to the "AI cost/latency controls" table-stakes item in the project's own pre-existing research
  and worth a line in the go-live budget check, though not a launch blocker.
- Sources: https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages (official — HIGH); pricing-change date corroborated by multiple 2026 WhatsApp API pricing blog posts (MEDIUM, consistent across sources).

### Display name rejection (MEDIUM)
Common, well-documented rejection causes worth a pre-submission checklist item if ALYASMEEN's
display name hasn't been approved yet:
- Name doesn't visibly match the Business Manager's legal/brand name or an associated
  website/social presence (the single most avoidable cause).
- Promotional words ("Best," "Official," "No.1," "Cheap," "Free") or the literal strings
  "WhatsApp"/"Facebook"/"Messenger" inside the name — instant rejection.
- All-caps names (unless the registered brand genuinely is an acronym).
- Names that read as a job function ("Customer Service," "Support Team") rather than a business
  name.
- An incomplete Business Manager profile is reportedly the single most common rejection cause,
  ahead of every wording issue combined — worth checking the Business Manager profile
  (address, website, category) is fully filled in before submitting/resubmitting.
- Appeals are rate-limited; hitting the appeal limit locks the name for 7-60 days — a reason to
  get the name right on the first submission rather than iterate live.

---

## Staged Pilot Design (10-30 orders/day, one operator, Palestine)

The project already has detailed, HIGH-confidence pre-existing research on this exact question,
written before any of Phases 1-5 existed (`.planning/research/FEATURES.md`:49,
`.planning/research/PITFALLS.md` Pitfall 16). It has not been superseded by anything more
specific — Phase 6 planning should treat it as the starting proposal, not reinvent it:

**Recommended minimum gate** (from the project's own research, not invented here):
- At least **7 consecutive pilot days**, **5 selected customers**, **20 production-like order
  lifecycles** (order through delivered/done, not just "confirmed").
- **Zero duplicate orders**, **zero restricted autonomous actions** (an order changed/cancelled
  automatically after leaving `to_do`, or any AI tool call the policy gate should have denied),
  **zero known critical defects** open at pilot end.
- **100% of handoffs visible to the aunt** — every one of the 5 handoff triggers
  (`keyword_request`, `unsupported_media`, `ai_failure`, `ai_requested`, `policy_denied`,
  source: ALYASMEEN/wiki/agent-safety.md) that fires during the pilot should be traceable back to
  a دschedule محادثات entry and (if applicable) an aunt response, with no silently-dropped case.
- Aunt completes at least one full operating shift with **zero developer intervention**.
- Successful restore/rollback drill evidence exists *before* the pilot starts, not during it —
  the backup drill is already done; the rollback drill (see below) is not.

**Given the current 10-30 orders/day volume**, 20 order lifecycles is achievable well inside 7
days even from a 5-customer cohort if each customer places 2-3 orders across the week — the
7-day floor is really about exercising different *operating conditions* (a weekend, a day
Khaled is unavailable, at least one real failure/retry/handoff event) rather than raw volume.
Worth flagging to the user as a "don't shorten this for the wrong reason" note if there's
pressure to compress the pilot.

**What to monitor daily during the pilot** (mapped to what already exists in this repo, not
invented):
- `/alerts` dashboard — dead-lettered webhook events and permanently-failed outbox jobs
  (source: app/routers/ui_api.py `GET /api/alerts`, app/templates/alerts.html).
- `/handoffs` (محادثات) — open vs resolved count, age of the oldest open item (no existing SLA
  timer in code today; a manual daily check is the only mechanism unless one is added).
- `/audit` (السجل) — a readable trail of every operator action, useful for the daily
  reconciliation pass the project's own pilot-pitfall research recommends
  (`.planning/research/PITFALLS.md` Pitfall 16's "Prevention" list: "Reconcile WhatsApp
  conversations, inbound events, orders, lines, outbox, and dashboard every day").
- The agent eval gate (`docs/EVAL_GATE.md`) — re-run before the pilot starts as the release gate
  it's designed to be, not during the pilot itself (it costs real API money and drives synthetic
  traffic, not real customer traffic).
- Direct DB spot-checks are the only way to see `webhook_events`/`outbox_jobs` row counts
  end-to-end — there is no dashboard rollup of "N events in, N processed, N still pending" today;
  worth deciding whether that's needed for the pilot or whether `/alerts` (which only surfaces
  *failures*, not healthy throughput) is sufficient.

### Rollback story — what actually exists today

No single documented "rollback runbook" exists in `docs/`. What's actually available, in order
of how surgical each is:

1. **Stop the Railway worker service only.** The web service keeps 200-ing and durably
   persisting inbound webhook events (source: app/routers/whatsapp.py:87-104); nothing gets
   processed — no AI replies, no order writes, no scheduled jobs, no outbound sends — until the
   worker restarts and drains the backlog. This is the cleanest available "pause everything
   downstream, lose nothing" lever in the current architecture, and it costs zero customer-data
   loss because the inbox/outbox pattern is durable by design. It is **not documented anywhere**
   as an operational procedure today.
2. **Redeploy with `USE_MOCK_WHATSAPP=1`.** Swaps the outbound sender to the console-printing
   mock (source: app/routers/whatsapp.py:8-11) and the inbound verifier along with it — stops
   real message delivery in both directions, but requires a full redeploy (not instant) and
   doesn't stop AI/DB spend on inbound processing.
3. **Detach the number in Meta Business Manager.** Heaviest and slowest — stops inbound at
   Meta's side entirely, likely complicates re-registration afterward. Reserve for a Meta-side
   incident (e.g., quality-rating restriction), not a code-side one.
4. **Railway image rollback to a previous successful deploy.** Available via Railway's own
   deployment-actions feature; reverts code, not data. **Has never been exercised on this
   project** (flagged as a risk before Phase 1 even started, source:
   `.planning/research/PITFALLS.md`:307, still true).

None of these four are wired into a single "if X happens, do Y" runbook a non-developer could
follow — that consolidation (not new code) is a natural Phase 6 deliverable.

---

## Training/Documentation Gap

**What Khaled (admin) already has:** `docs/OPERATOR_ACCOUNTS.md` (account/MFA lifecycle),
`docs/EVAL_GATE.md` (pre-release AI regression check), `docs/BACKUP_DRILL.md` (backup/restore +
DR), `scripts/manage_operators.py` (create/list/reset-mfa/reset-password CLI). All in English,
all runbook-style, all already written to the same "practical register... written for Khaled to
run before shipping a change, not for a pipeline to run automatically" standard
(source: docs/EVAL_GATE.md's own framing, line 8-9) — Phase 6's admin-facing artifacts should
match this existing house style rather than invent a new one.

**What Khaled does not have:** a single rollback/incident runbook (see above), a documented Meta
go-live checklist (asset IDs, template decisions, current API version — the project's own
pre-existing pitfalls research explicitly recommends recording these "without storing secret
token values," source: `.planning/research/PITFALLS.md`:50), and a written go/no-go checklist
tying the four success criteria to concrete evidence artifacts (this RESEARCH.md's readiness
inventory above is a starting point for that, not a substitute).

**What the aunt already has:** a dashboard that does most of the explaining itself — this is a
genuine strength of Phases 3-5's UX work, not a gap. Plain-Arabic alert cards state
"what_happened"/"what_to_do" per item (source: app/routers/ui_api.py `_frame_alert`,
app/templates/alerts.html), the audit trail renders every action as a natural Arabic sentence
(source: app/templates/audit.html `describe()`), and the handoff conflict modal explains itself
in-context (source: app/templates/orders.html, 05-08).

**What the aunt does not have:** anything she can read *without* opening the dashboard, offline,
during a genuine incident (e.g., "the site won't load — what do I check on my phone before
calling Khaled?"). The project's own pre-existing research called this out by name before any
code existed (`.planning/research/PITFALLS.md` Pitfall 17: "one-page Arabic-first runbooks for
common incidents and escalation") and it remains true today.

---

## Test-coverage requirement (REQ-nfr-test-coverage)

**Measured, not estimated** — a live run on this branch:

```
pytest --cov=app --cov-report=term-missing -q
483 passed, 3 skipped, 1 deselected
TOTAL coverage: 85.40%  (fail_under = 85, source: pyproject.toml:41-42)
```

The 85% gate itself already exists in `pyproject.toml`'s `[tool.coverage.report]` section, with
a comment noting it is "available but not enabled today" — no default `pytest` invocation
includes `--cov`, and there is no CI to run it automatically (source: pyproject.toml:60-61,
confirmed no `.github/` directory anywhere in the repo).

**Where the coverage is weakest** (worth knowing before deciding whether 85% overall is "enough"
given `REQ-nfr-test-coverage`'s own wording — "core bot logic + API endpoints,"
source: .planning/intel/requirements.md:64):

| File | Coverage | Note |
|---|---|---|
| `app/worker.py` | 30% | Scheduler wiring/startup glue — low logic density, arguably acceptable to leave thin |
| `app/routers/broadcast.py` | 52% | `/broadcast/improve` — AI tone-improvement helper, not core order path |
| `app/routers/whatsapp.py` | 70% | The actual webhook entry point — worth a closer look given its criticality |
| `app/routers/auth_routes.py` | 73% | Login/MFA/session routes |
| `app/services/auth.py` | 72% | Supabase Auth wrapper (admin ops, TOTP) |
| `app/services/ai_service.py` | 77% | Prompt/tool-call construction |
| `app/ai/retriever.py` | 81% | Product search/catalog loading |

Every genuinely core file (`processor.py` 92%, `policy.py` 98%, `handoff.py` 94%,
`ui_api.py` 84%, `database.py` 90%) is already comfortably at or above 85% individually — the
overall number being pulled down mostly by admin/auth-flow edge cases and the worker's own
process-startup code, not by the bot's decision logic. This is a reasonable state to describe as
"the requirement's intent is met," but whether to (a) leave it as a manual, EVAL_GATE.md-style
documented check, (b) wire `--cov` into default `addopts` so a stray regression is caught
automatically, or (c) invest in real CI for the first time is a genuine scope decision for this
phase, not something research can resolve.

---

## Standard Stack (for whatever net-new artifacts this phase produces)

Given the phase is mostly documentation + external-process work, not new application code, there
is little new library surface. What's relevant:

| Tool | Already in repo? | Purpose here |
|---|---|---|
| `pytest-cov` | Installed (7.1.0, confirmed via `pip show`), not in `requirements.txt` as an explicit pin | Only tool needed to make REQ-nfr-test-coverage measurable/enforceable |
| Meta Graph API (Cloud API) | Yes, `v19.0` hard-coded | Bump version, decide on template support |
| Railway deployment actions | Platform feature, unused for rollback so far | The rollback mechanism to document/drill, not build |
| Sentry / external uptime checker | **Not present**, was originally recommended (`.planning/research/STACK.md`) | Explicit go/no-go decision needed — see Open Questions |

**Don't hand-roll:** if the user decides Meta templates are needed for aunt/admin alerts or the
follow-up message, do not hand-roll template submission/tracking — Meta's own template
management API + the Business Manager UI is the standard path; there is no reason to build a
custom template-state table before confirming templates are actually required (see Open
Questions — the 24h-window risk may be acceptable to just monitor instead).

---

## Common Pitfalls (phase-specific, verified against this repo)

### Pitfall: Free-form aunt/admin alerts silently rejected outside the 24h window
**What goes wrong:** `AUNT_PHONE`/`ADMIN_PHONE` alerts (new order, permanent failure, new-device
login) are ordinary `queue_text` sends — if the aunt or Khaled hasn't messaged the WABA number
within the last 24 hours, Meta will reject the send as a policy violation (error 131047) rather
than deliver it late.
**Why it happens:** The architecture treats `AUNT_PHONE`/`ADMIN_PHONE` as "internal" recipients,
but Meta's API has no concept of internal vs. external WhatsApp numbers — the 24h rule is
universal.
**How to avoid:** Either (a) accept the risk and rely on the fact that an actively-operating
aunt/admin will naturally message the bot number often enough to keep the window open, with a
documented awareness that this can silently fail during a quiet period, or (b) get at least one
Utility-category template approved specifically for operational alerts. This is a real decision
this research surfaces, not a bug to fix silently.
**Warning signs:** An alert that the code queued (visible in `outbox_jobs`) never arrives on
WhatsApp, with no error surfaced anywhere in-app — because `whatsapp_meta.py` raises on non-2xx
already, the failure *should* land in `/alerts` as a dead-lettered outbox job (source:
app/services/processor.py `notify_permanent_failure`), so this is at least visible today, just
not obviously diagnosed as a template-policy issue rather than a generic send failure.

### Pitfall: Treating the 05-10 checkpoint as parallel-safe with Phase 6 planning
**What goes wrong:** Phase 6 formally depends on Phase 5 (source: .planning/ROADMAP.md:110), and
Phase 5's own final plan (`05-10-PLAN.md`) is only partially executed — the operator accounts do
not exist yet, and the plan's own Task 1 note is explicit: "MUST NOT push until accounts exist —
new auth with zero accounts = dashboard lockout" (source: STATE.md's Current Focus paragraph).
**Why it matters for Phase 6:** Any live verification work this phase's plans want to do against
the deployed dashboard (the pilot, the aunt walkthrough, the go-live checklist) is blocked until
05-10 is fully closed out, not just "mostly done."
**How to avoid:** Treat 05-10's remaining human-gated tasks as a hard prerequisite gate for any
Phase 6 plan that touches the live system, not as something Phase 6 can quietly finish as a side
effect.

### Pitfall: Stale wiki/docs describing removed subsystems
**What goes wrong:** `ALYASMEEN/wiki/scheduler-jobs.md` still describes a `retry_queue.py`
job that was deleted in Phase 4 (source: STATE.md's Technical Debt section, "retry_queue.py
deleted entirely"). `ALYASMEEN/wiki/whatsapp-bot-brain.md` and `ai-service.md` are flagged
stale by `agent-safety.md`'s own banner. `ALYASMEEN/wiki/alyasmeen-auntops.md` still claims
`app/data/knowledge/` is empty (it has 6 files) and gives the state as "March 2026" alongside a
"per source" caveat that is itself now 2.5 months stale relative to the actual repo.
**Why it matters for Phase 6:** if this phase produces any new wiki pages or CLAUDE.md updates
(likely, since it's the final phase), someone reading the vault for "how does this work" during
the pilot could act on outdated information.
**How to avoid:** A vault sweep (matching the pattern 03-08 already did for `agent-safety.md`)
is reasonable in-scope Phase 6 documentation work, not scope creep — the phase produces
aunt/admin-facing docs anyway.

### Pitfall: Requirements-doc milestone-numbering drift (cosmetic, not blocking)
`.planning/REQUIREMENTS.md`'s traceability table still labels this phase's requirements
"Go-Live (M5)" (source: .planning/REQUIREMENTS.md:46) while `.planning/ROADMAP.md` calls it
"Phase 6 (M6)" throughout — a relic of the roadmap being split into 6 phases after the original
5-milestone research (`.planning/PROJECT.md`, `.planning/.continue-here.md`) was written. Doesn't
block planning, but worth a one-line fix in REQUIREMENTS.md while this phase's docs are being
touched anyway.

---

## Pre-existing project research (do not re-derive — read these directly)

This project ran a full pre-Phase-1 research pass on exactly this domain in June 2026, before
any of the current implementation existed. It is still HIGH confidence for anything that hasn't
been resolved by Phases 1-5 since (cited above wherever used), and is the deepest source
available for Phase 6 planning:

- `.planning/research/PITFALLS.md` — 20 numbered pitfalls with prevention/evidence/
  contingency for each, a Go/No-Go checklist (lines 760-776), and an M5(=M6)-specific ownership
  row (line 28).
- `.planning/research/FEATURES.md` — the "Staged pilot and controlled cutover" table-stakes row
  (line 49) is the source for the pilot gate numbers used above; also has a "Cutover readiness
  dashboard" differentiator (line 65) worth considering as a lightweight artifact.
- `.planning/research/ARCHITECTURE.md` — the M5(=M6) section (lines 737-752) and the
  Observability/Rollback sections (350-500) are the most directly reusable for this phase's
  monitoring/rollback decisions.
- `.planning/research/STACK.md` — the original Sentry/Better Stack monitoring recommendation
  (lines 187, 302) that was never implemented; still the reasonable default if the user decides
  external monitoring is in scope.
- `.planning/PROJECT.md` — the original "Production Definition" (9-point list, lines 171-183)
  and "Key Decisions" table are the closest thing to a charter for what "done" means.

None of these are phase-6-specific files in the current GSD structure (they predate the 6-phase
roadmap), so the planner should read them directly rather than expect this RESEARCH.md to have
copied everything forward.

---

## Open Questions

These need `/gsd:discuss-phase 6` (or direct user answers) before planning can proceed —
research cannot resolve any of them from the repo alone:

1. **Meta WABA current status.** Is the business review still pending, approved, or rejected?
   Is a new `WA_META_TOKEN` (system-user, permanent) already generated? What is the SSL/domain
   status on `alyasmeen.org`? (CLAUDE.md/STATE.md both say "pending" as of the last update —
   this is live external state.)

2. **Message templates: build or accept the risk?** Given the 24h-window finding above, does
   Khaled want to invest in getting at least one Utility-category template approved for
   aunt/admin operational alerts (a real, if small, build item), or explicitly accept that these
   may occasionally fail outside an active session and rely on `/alerts`'s existing dead-letter
   visibility to catch it?

3. **External monitoring: in scope or explicitly deferred?** The original pre-project research
   recommended Sentry + an external uptime/heartbeat checker; none exists today. Is the existing
   internal stack (`/health`, `/alerts`, WhatsApp failure pings, structured logs) considered
   sufficient for a 10-30 orders/day single-operator business, or does "monitoring... signed off"
   in success criterion 4 require adding an external tool first?

4. **Pilot cohort and duration.** Does the pre-existing research's recommendation (5 customers,
   7 consecutive days, 20 order lifecycles) still fit, or does the user want to adjust given
   time already elapsed since the original one-month target (set 2026-06-14, now 2026-08-28)?

5. **Rollback: document only, or drill and record?** `docs/BACKUP_DRILL.md` set the precedent of
   actually *executing* a drill and logging the result. Should rollback get the same treatment
   (a real Railway rollback + worker-stop drill, logged), or is documenting the procedure without
   executing it acceptable given time constraints?

6. **Test-coverage gate: manual doc, wired into pytest, or real CI?** REQ-nfr-test-coverage is
   already met (85.40%). Does the user want (a) a `docs/COVERAGE_GATE.md` mirroring
   `EVAL_GATE.md`'s "human runs this before release" pattern, (b) `--cov` added to default
   `addopts` so `pytest -q` itself enforces it, or (c) the repo's first-ever `.github/` CI
   workflow?

7. **Aunt cheat-sheet: format and delivery.** A one-page Arabic reference is the clear gap.
   Printed and left with her physically, a PDF she can reopen, or a page inside the dashboard
   itself (e.g., a `/help` route)? Does it need Khaled's review/approval before being considered
   "final," given the target reader can't review English planning docs herself?

8. **Sign-off authority.** Is Khaled the sole sign-off for all four success criteria (reasonable
   given the solo-owner/student context established in `.planning/PROJECT.md`), or does the aunt
   need to explicitly co-sign criterion 3 (her own competency) separately from Khaled's
   technical sign-off on 1/2/4?

9. **05-10 completion gate.** Should Phase 6 planning proceed now (producing plans that assume
   05-10 finishes first as a hard prerequisite), or should the orchestrator wait for 05-10 to
   fully close before spawning Phase 6 plans at all?

---

## Sources

### Primary (HIGH confidence — direct code/test inspection, this repo)
- app/routers/whatsapp.py, app/services/whatsapp_meta.py, app/services/processor.py,
  app/services/handoff.py, app/services/followup.py, app/services/monthly_report.py,
  app/main.py, app/worker.py, railway.json, Procfile, pyproject.toml, requirements.txt,
  supabase/migrations/*.sql, app/db/schema.sql — read directly.
- Live `pytest --cov=app --cov-report=term-missing -q` run on this branch, 2026-08-28: 483
  passed, 3 skipped, 1 deselected, 85.40% coverage.
- `grep` verification of: no Sentry/UptimeRobot/Datadog/Prometheus references anywhere in
  `app/`/`docs/`; no `.github/` directory; no `image_url` column in any migration; no kill-switch
  env vars (`AGENT_AUTONOMY`, etc.) in `app/services/config.py`; `app/data/knowledge/` contains 6
  files (not empty).
- docs/BACKUP_DRILL.md, docs/EVAL_GATE.md, docs/OPERATOR_ACCOUNTS.md — read in full.
- .planning/STATE.md, .planning/ROADMAP.md, .planning/REQUIREMENTS.md,
  .planning/intel/requirements.md, .planning/phases/05-operator-security-ux/05-10-PLAN.md — read
  in full.
- ALYASMEEN/wiki/agent-safety.md, design-decisions.md, web-dashboard.md,
  whatsapp-meta-integration.md, scheduler-jobs.md, alyasmeen-auntops.md — read via the vault
  per CLAUDE.md's required workflow.

### Secondary (MEDIUM confidence — pre-existing project research, June 2026, largely still valid)
- .planning/research/PITFALLS.md, FEATURES.md, ARCHITECTURE.md, STACK.md — pre-Phase-1 research
  written for this exact project; cited throughout above wherever still applicable. Written
  before Phases 1-5 existed, so cross-checked against current code rather than trusted blindly —
  most of its M1-M4 findings are now resolved; its M5(=M6) findings are largely still open.
- .planning/PROJECT.md, .planning/.continue-here.md — original 5-milestone charter and
  paused-session context, useful for understanding why the requirements-doc numbering (M5) and
  roadmap numbering (Phase 6/M6) disagree.
- .planning/codebase/CONCERNS.md — dated 2026-06-13, pre-hardening; **treated as historical, not
  current** — its top findings (webhook envelope parsing, silent send failures) are confirmed
  resolved by direct code inspection above.

### Tertiary (LOW-MEDIUM confidence — WebSearch, 2026)
- WhatsApp Cloud API messaging-limits and 24h-window rules: fetched directly from
  https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits and
  .../messages/send-messages (HIGH confidence — official source, fetched, not just search
  snippets).
- Graph API current version number: MEDIUM confidence only — search results disagreed (v21 vs
  v25 claims from different aggregator sources); recommend the planner/executor check
  https://developers.facebook.com/docs/graph-api/changelog directly before committing to a
  specific version bump.
- 2026-10-01 service-message pricing change, display-name rejection causes, business-verification
  tier mechanics: MEDIUM confidence — consistent across multiple third-party sources
  (Wati, Chatarmin, Ominiflow, Uptail, PayPerWA, etc.) but not independently confirmed against a
  single official Meta page for every specific claim.

---

## Metadata

**Confidence breakdown:**
- Repo readiness inventory (what exists/doesn't): HIGH — verified by direct code reads, grep,
  and a live test/coverage run, not inference.
- Meta WABA 2026 specifics: MEDIUM-HIGH for official-doc-sourced claims (tiers, 24h window),
  MEDIUM for aggregator-sourced claims (exact current Graph API version, pricing-change date,
  display-name rejection specifics).
- Staged pilot design: HIGH for the gate numbers themselves (sourced from this project's own
  prior HIGH-confidence research, not invented here), MEDIUM for how well they still fit given
  time elapsed since that research was written.
- Training/documentation gap: HIGH — confirmed by direct enumeration of `docs/` and comparison
  against what the dashboard templates already render.
- Test-coverage requirement: HIGH — directly measured, not estimated.

**Research date:** 2026-08-28
**Valid until:** Re-verify Meta-specific claims (tiers, API version, pricing date) before
go-live if more than ~30 days pass, since Meta policy/version details move faster than the rest
of this document. The repo-state findings (readiness inventory, coverage number, doc gaps) are
valid until the next meaningful code/doc change, not time-based.
