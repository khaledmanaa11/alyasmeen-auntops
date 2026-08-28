# ALYASMEEN AuntOps Production Readiness

## What This Is

ALYASMEEN AuntOps is an existing WhatsApp ordering agent and web dashboard for a small
Palestinian skincare business. Customers can browse products, receive Arabic or English
assistance, manage a cart, choose pickup or delivery, and place orders; the owner's dashboard
supports order, product, reporting, and broadcast workflows.

This project takes the current system from a functional development implementation to a
real production service that the owner's aunt can safely operate with real WhatsApp customers.
The separate public website is not part of this project and will be planned later as its own
build.

## Core Value

Customers can reliably place and manage real orders through WhatsApp, while the aunt retains
clear control over exceptions and can operate the business without technical assistance.

## Requirements

### Validated

- The bot supports Arabic- and English-language customer conversations.
- Customers can browse the live product catalog and view product information.
- Customers can add products to a persistent cart and clear or inspect that cart.
- Customers can choose pickup or delivery and provide a reusable delivery address.
- Customers can confirm an order, receive an order number, and track its status.
- Confirmed orders and order lines are stored in Supabase.
- The aunt receives a WhatsApp notification when a customer confirms an order.
- The dashboard displays and updates orders and notifies customers about status changes.
- The dashboard supports product catalog management, business statistics, and broadcasts.
- Claude can use tools to browse products, mutate carts, retrieve order status, and save an
  address.
- Scheduled follow-ups, monthly reports, retries, and PDF invoice generation exist.
- Unit and mocked integration tests cover the principal development-mode workflows.

### Active

- [ ] Production Supabase has versioned, reproducible schema migrations, least-privilege
  access, appropriate RLS/key usage, verified backups, retention rules, and recovery
  procedures.
- [ ] The FastAPI service securely accepts real Meta webhook envelopes, verifies signatures,
  handles duplicate deliveries, applies rate limits, exposes meaningful health checks, and
  can be deployed and rolled back predictably.
- [ ] The WhatsApp agent handles ordinary orders autonomously and routes uncertain or risky
  cases to a human without making unsupported commitments.
- [ ] Customers can automatically modify or cancel only `to_do` orders; requests involving
  later statuses are routed to the aunt.
- [ ] The agent never autonomously substitutes products, changes prices, promises refunds,
  or gives medical guidance.
- [ ] Voice notes, images, payment questions, possible skin or medical reactions, angry
  complaints, custom requests, and unresolved uncertainty trigger human handoff.
- [ ] Human handoff pauses automated replies, tells the customer that a person will respond,
  alerts the aunt on WhatsApp, and creates a visible dashboard inbox item until resolution.
- [ ] Handoff records preserve the relevant conversation, trigger reason, agent decision,
  aunt resolution, and outcome for audits and future agent evaluation.
- [ ] AI behavior is evaluated against representative Arabic, English, noisy, adversarial,
  and end-to-end ordering scenarios with explicit release thresholds, cost controls, and
  deterministic fallbacks.
- [ ] The dashboard uses production-grade authentication, CSRF protection, input validation,
  secure sessions/cookies, login abuse protection, and authorization checks.
- [ ] Security, structured logging, metrics, error reporting, alerting, audit trails, and
  operational runbooks are added incrementally across all milestones rather than postponed
  until launch.
- [ ] Meta Business and WhatsApp Business Account onboarding is completed for the real
  business number early enough not to block the launch.
- [ ] A staged pilot with the aunt and selected customers proves the full real-world order
  lifecycle before public cutover.
- [ ] The final system has no known critical security defects, tested backup recovery,
  active monitoring, a documented rollback process, and operator training.
- [ ] The production system is ready for handoff within one month.

### Out of Scope

- Public marketing or commerce website - this will be a separate future project.
- Integrated online payments - v1 uses cash or other manually managed payment.
- Courier or delivery-provider integration - the aunt coordinates delivery and pickup.
- Autonomous refunds, discounts, price changes, or product substitutions - these require
  aunt approval.
- Medical diagnosis or treatment advice - possible adverse reactions and medical questions
  always require human handoff.
- Immediate unrestricted public launch - rollout begins with a controlled pilot.
- Unnecessary payment or sensitive medical data storage - the system should avoid collecting
  it.

## Milestone Strategy

### M1: Supabase to Production

Establish a reproducible and recoverable data foundation: authoritative schema, migrations,
constraints, indexes, safe key usage, RLS/access decisions, retention, backups, restoration,
and production data operations.

### M2: FastAPI to Production

Harden and deploy the application boundary: real Meta payload parsing and signature
verification, idempotency, rate limiting, health and readiness checks, secure configuration,
background-job behavior, CI/CD, deployment, and rollback.

### M3: Agent to Production

Make customer service dependable: intent and tool reliability, hybrid autonomy rules,
automatic `to_do` order changes, human handoff, fallbacks, cost and latency controls,
evaluation datasets, release thresholds, and auditability.

### M4: UI to Production

Make the aunt's operating surface secure and complete: real authentication, authorization,
CSRF protection, validation, session management, handoff inbox, order-change visibility,
audit history, and operator-friendly recovery paths.

### M5: Go-Live

Prove and launch the integrated service: complete real Meta WABA setup, production domain and
TLS verification, end-to-end tests, monitoring and alerting validation, disaster recovery and
rollback drills, aunt training, pilot operation, defect closure, and controlled cutover.

The milestones describe primary ownership, not isolation. Meta registration starts early;
security, observability, testing, documentation, and operational readiness are acceptance
criteria throughout M1-M4 and are validated together in M5.

## Context

- The current architecture is a layered FastAPI modular monolith serving the WhatsApp
  webhook, server-rendered dashboard, JSON APIs, and in-process APScheduler jobs.
- Supabase PostgreSQL is accessed over HTTPS through `app/db/database.py` and custom
  `run_query`/`run_exec` RPC functions.
- Meta Cloud API is used for real WhatsApp messaging; development currently defaults to a
  mock sender.
- Anthropic Claude Haiku provides conversational responses and tool use.
- Expected business volume is small, approximately 10-30 orders per day, with one primary
  operator.
- Existing codebase analysis identified production blockers including incompatible real
  Meta webhook parsing, missing webhook authentication, schema drift, insecure dashboard
  defaults, unprotected development endpoints, weak login/session security, and absent
  external monitoring.
- Meta onboarding has started but the real business number is not yet fully registered and
  has encountered problems. This is an immediate critical-path dependency.
- The owner is still learning production operations, so each milestone must include clear
  explanations, verification evidence, runbooks, and explicit go/no-go criteria.
- Conversations and human-handoff records are retained for 12 months and then anonymized.
  Long-term AI evaluation data is anonymized before reuse. Orders and invoices follow
  separately defined legal/accounting retention requirements.

## Constraints

- **Timeline**: Production handoff is targeted within one month - scope must prioritize
  launch blockers and measurable safety over optional polish.
- **Architecture**: Preserve the existing modular monolith unless evidence shows it cannot
  meet reliability requirements at the expected volume.
- **Database access**: Current Supabase HTTPS/RPC architecture is the starting point; its
  privilege and SQL-execution model must be audited before production approval.
- **Messaging**: Real operation depends on successful Meta Business/WABA registration and
  webhook approval for the business number.
- **Payments**: Cash or manually managed payment only for this release.
- **Fulfillment**: Pickup and aunt-managed delivery only; no courier integration.
- **Autonomy**: Ordinary low-risk orders are autonomous; uncertainty and designated risky
  categories require human control.
- **Order changes**: Automatic cancellation/modification is allowed only while status is
  `to_do`; all later changes require aunt intervention.
- **Privacy**: Minimize personal data, avoid sensitive medical/payment data, restrict access,
  and anonymize retained conversation/evaluation records according to policy.
- **Operations**: The aunt must be able to understand open work, handoffs, failures, and
  recovery actions from the UI and documented procedures.
- **Quality**: A milestone is complete only when implementation, automated verification,
  production-like validation, documentation, rollback, and acceptance evidence are complete.

## Production Definition

The project is ready to hand over only when:

1. No known critical security or data-integrity issue remains.
2. Database migrations and a restore from backup have been tested.
3. Real Meta webhook traffic and outbound messaging work with the production number.
4. Ordinary orders, eligible changes, status updates, notifications, invoices, retries, and
   human handoffs pass realistic end-to-end tests.
5. AI evaluation thresholds and cost/latency budgets pass on representative data.
6. Monitoring and actionable alerts cover service, database, messaging, AI, and background
   job failures.
7. Deployment and rollback procedures have been exercised.
8. A staged pilot with selected customers completes successfully.
9. The aunt can operate daily workflows and resolve handoffs using documented instructions.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use five production-readiness milestones | Provides component ownership and an integrated launch gate | Pending |
| Keep the modular monolith initially | Expected scale does not justify distributed-system complexity | Pending |
| Use hybrid agent autonomy | Automates ordinary orders while preserving human control over risk and ambiguity | Pending |
| Pause automation during human handoff | Prevents the agent from contradicting the aunt or compounding a sensitive case | Pending |
| Allow automatic order changes only in `to_do` | Balances customer convenience with fulfillment safety | Pending |
| Start Meta WABA work before M5 | Registration is an external critical-path risk that can block launch | Pending |
| Add security and observability throughout | These cannot be safely bolted on only at final cutover | Pending |
| Pilot before public launch | Limits customer impact while real workflows and operator readiness are proven | Pending |
| Retain conversations/handoffs for 12 months, then anonymize | Supports improvement and audits while limiting long-term personal-data exposure | Pending |
| Treat the website as a separate project | It is a new product build, not required to productionize AuntOps | Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? Move to Out of Scope with reason.
2. Requirements validated? Move to Validated with phase reference.
3. New requirements emerged? Add to Active.
4. Decisions to log? Add to Key Decisions.
5. "What This Is" still accurate? Update if drifted.

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections.
2. Core Value check - confirm it remains the right priority.
3. Audit Out of Scope - confirm reasons remain valid.
4. Update Context with the current operational state.

---
*Last updated: 2026-06-14 after initialization*
