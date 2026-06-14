# Feature Landscape

**Domain:** Production readiness for a small-business WhatsApp commerce agent
**Project:** ALYASMEEN AuntOps Production Readiness
**Researched:** 2026-06-14
**Overall confidence:** HIGH for platform/security requirements; MEDIUM for proposed numeric launch thresholds

## Scope

The product already supports shopping and order operations. The launch milestone should not
expand the consumer feature set. It should make existing behavior safe, observable,
recoverable, policy-compliant, and operable by one nontechnical owner.

The most important product principle is:

> Automate ordinary, reversible, well-understood actions. Pause and hand off anything
> uncertain, sensitive, irreversible, policy-sensitive, or inconsistent with current order
> state.

## Table Stakes

Missing any of these capabilities should block public launch.

| Capability | Why Expected | Complexity | Dependencies | Measurable Acceptance Implication |
|------------|--------------|------------|--------------|-----------------------------------|
| Versioned production schema and data constraints | Orders, lines, sessions, handoffs, retries, and audit records cannot depend on dashboard-created schema or undocumented drift. | High | Supabase migration workflow; authoritative schema; deployment pipeline | A blank production-like project can be created only from migrations; schema drift check passes; required foreign keys, uniqueness rules, status constraints, and indexes are verified automatically. |
| Backup, restore, and reconciliation procedure | A backup that has never been restored is not a recovery capability. Supabase also notes that database backups do not restore deleted Storage objects. | Medium | Schema stability; backup plan; invoice/media inventory; runbook | Restore is exercised before pilot; recommended initial targets are RPO <= 24 hours and RTO <= 4 hours; a post-restore script reconciles order counts, totals, invoice references, and pending work. |
| Least-privilege database access | The current broad SQL RPC model and service credentials create a high-impact compromise path. Supabase requires RLS on exposed-schema tables and warns that service keys bypass RLS. | High | Access inventory; backend-only secrets; RLS/role design | No service key is present in browser assets or logs; exposed tables have explicit policies; unauthorized access tests fail closed; production secret rotation is documented and tested. |
| Authenticated owner dashboard with MFA | The dashboard exposes customer data and state-changing order controls. A static SHA-256 password cookie is not sufficient. | Medium | Managed identity or proven password hashing; TOTP/recovery flow; secure session store | No default credentials; TOTP MFA enabled for the owner; recovery codes tested; login throttling works; all cookies are `Secure`, `HttpOnly`, and appropriately `SameSite`; idle and absolute timeouts are server-enforced. |
| CSRF protection and server-side authorization | Every dashboard mutation can otherwise be triggered from an attacker-controlled page or an untrusted client. | Medium | Secure sessions; centralized auth dependency | Every state-changing browser request validates CSRF protection and authorization; negative tests cover missing/invalid tokens and unauthenticated API calls; UI visibility is never treated as authorization. |
| Real Meta webhook normalization and signature verification | The current flat development payload rejects the real nested envelope, and unsigned POSTs can trigger orders and AI spend. | High | Meta app secret; raw request body; production WABA/number; valid TLS | Official text, interactive, status, unsupported-media, batched, empty, and malformed envelopes are tested; invalid or missing signatures are rejected before parsing or AI calls; GET verification still works. |
| Idempotent inbound processing and side effects | Webhook delivery and application retries must never create duplicate orders, duplicate cart mutations, duplicate aunt alerts, or duplicate customer messages. | High | Persisted Meta message IDs; unique constraints; transaction boundaries; outbox/retry design | Replaying the same `wamid` 10 times produces one business mutation and one logical outbound action; concurrent confirm requests produce one order; duplicate status events are harmless; idempotency survives process restart. |
| Explicit order state machine | Change/cancel safety depends on authoritative states and legal transitions, not UI conventions. | Medium | Database constraints; audit events; dashboard status actions | Transition matrix is enforced server-side; invalid transitions return a stable error and create no partial write; direct database tests confirm status constraints. |
| Safe order modification and cancellation | Customers expect corrections, but edits after fulfillment work starts can cause inventory, delivery, and invoice errors. | High | State machine; customer/order identity; atomic repricing; handoff | Only orders still in `to_do` can be changed or cancelled automatically; a concurrent move out of `to_do` wins and forces handoff; changes atomically update lines and totals, retain before/after state, and send a revised summary for confirmation; cancellation never hard-deletes the order. |
| Human handoff with automation pause | Meta's current policy permits automation only with prompt, clear, direct escalation paths. Sensitive or unresolved cases must not continue receiving AI replies. | High | Handoff state; dashboard inbox; aunt notification; business-hours copy | Voice notes, images, payment questions, possible reactions/medical issues, angry complaints, custom requests, explicit human requests, repeated failures, and unresolved uncertainty trigger handoff; customer acknowledgment is sent once; aunt alert and inbox item appear within 60 seconds; no automated reply is sent until the owner explicitly resumes or resolves. |
| Handoff ownership and aging | With one operator, unowned exceptions become invisible customer failures. | Medium | Handoff inbox; notifications; operator status model | Every open handoff has reason, severity, age, customer, related order, last message, and next action; overdue items are visually distinct; resolve/reopen actions are audited; the owner can clear the queue without database access. |
| Meta opt-in, template, window, and opt-out enforcement | Meta requires opt-in for business-initiated contact, approved templates to initiate conversations, and templates outside the 24-hour service window. The existing 3-day follow-up and most broadcasts are therefore not launch-ready as arbitrary text messages. | High | Consent records; approved templates; last-user-message timestamp; template status webhooks | Follow-ups, broadcasts, delayed order updates, and monthly owner messages select an approved template when required; non-opted-in or opted-out recipients are excluded; `STOP`/equivalent requests suppress future marketing; template name/category/version and consent basis are recorded for every initiated message. |
| Meta quality and policy health monitoring | Negative feedback, low quality, policy violations, or template disablement can restrict or disable messaging. | Medium | WABA webhook subscriptions; Business Manager admin contact; alerting | `account_update`, template-status, phone-quality, send-error, delivery, and read events are stored and surfaced; policy restriction alerts reach a channel other than the affected WhatsApp number; admin email/contact details are verified. |
| Skincare catalog and claims policy review | Meta restricts commerce involving medical and healthcare products. Cosmetics must not be presented with diagnosis, treatment, cure, or unsafe supplement claims. | Medium | Catalog export; product classification; owner review; legal/policy escalation path | Every active product and template passes a documented pre-launch review; unsupported therapeutic claims are removed; possible reactions and medical questions always hand off; adding a flagged product requires owner acknowledgement and policy review. |
| AI action allowlist and deterministic guardrails | Prompt instructions alone cannot safely authorize refunds, price changes, substitutions, medical advice, or late order edits. | High | Tool schemas; server-side policy layer; state machine; handoff | Restricted actions have no callable tool or fail server-side regardless of model output; prices and products come from the database; each tool call validates customer, order, state, and arguments; AI outage or invalid output cannot mutate business state. |
| Deterministic AI fallback | Claude can rate-limit, overload, time out, return malformed tool arguments, or be unavailable. The customer still needs a safe response. | Medium | Hard-command paths; retry policy; handoff | Timeouts, 429s, 5xx errors, malformed tool calls, and exhausted budgets produce a short bilingual fallback or handoff, never an invented answer; bounded retries honor provider guidance; provider request IDs are logged without transcript leakage. |
| Release-gated AI evaluations | Unit tests do not establish that a bilingual agent behaves safely on real language, ambiguity, noise, or adversarial requests. Anthropic recommends task-specific, multidimensional evals that mirror real traffic and include edge cases. | High | Versioned eval dataset; graders; prompt/model versioning; CI release gate | Critical safety set has 100% correct refusal/handoff; order-state and tool-side-effect scenarios pass >= 95%; no catalog/price claim lacks a source-of-truth reference; Arabic, English, code-switching, noisy text, prompt injection, duplicate delivery, and end-to-end flows are represented; any prompt/model/tool change reruns the gate. |
| AI latency and cost controls | An unauthenticated webhook or tool loop can create uncontrolled spend and poor response times. Anthropic exposes spend/rate controls, usage data, retry headers, and token metrics. | Medium | Per-request usage capture; workspace/provider limits; alerting | Maximum model calls and tokens per turn are enforced; daily/monthly soft alerts and a hard stop are configured; deterministic commands retain p95 <= 2 seconds; initial AI target is p95 <= 8 seconds under production-like load; budget exhaustion falls back safely. |
| Privacy notice, minimization, and retention enforcement | Meta requires notices/consent and forbids requesting sensitive identifiers. The project already chose 12-month conversation/handoff retention followed by anonymization. | High | Data inventory; retention classes; deletion/anonymization job; published notice | Public privacy notice describes WhatsApp, Meta, Anthropic, purposes, retention, and contact method; full card/account/ID data is neither requested nor stored; detected sensitive values are redacted; conversations/handoffs older than 12 months are anonymized automatically; orders/invoices follow a separate documented accounting schedule. |
| Auditable business actions | The owner must be able to answer who changed an order, why automation handed off, and whether a message was sent. | High | Append-only audit events; correlation IDs; actor model | 100% of state-changing actions record timestamp, actor (`customer`, `agent`, `owner`, `system`), action, reason, before/after summary, related order/customer, inbound `wamid`, outbound message ID, and deployment/prompt version where relevant; normal UI actions cannot edit audit history. |
| Operator work queue and daily control loop | A nontechnical owner needs one place to see work, not separate logs, cron output, and database tables. | Medium | Handoff inbox; retry queue; status events; audit summary | A "Needs attention" view combines open handoffs, failed sends, exhausted retries, stale `to_do` orders, scheduler failures, and policy/template warnings; each item has one recommended next action; daily opening/closing checklist is documented and usability-tested with the owner. |
| External monitoring and actionable alerts | In-process logs cannot detect a dead deployment, broken webhook subscription, expired token, or stopped scheduler. | High | External uptime check; structured logs; metrics/error reporting; secondary alert channel | External checks cover liveness and readiness; alerts fire within 5 minutes for sustained webhook failure, outbound failure spike, database outage, AI failure spike, scheduler lateness, cost threshold, backup failure, or policy restriction; alerts contain impact and runbook link but no customer message content. |
| Incident response, kill switches, rollback, and recovery | One owner needs simple containment actions when automation is wrong or an integration is failing. NIST recommends integrating preparation, detection, response, and recovery into risk management. | High | Feature flags; deployment rollback; runbooks; backups; contact list | The owner or maintainer can disable AI replies, broadcasts, follow-ups, or all outbound automation independently without deploy; rollback to the previous release is rehearsed; severity definitions, contacts, customer communication templates, evidence preservation, and post-incident review are documented. |
| Staged pilot and controlled cutover | A full public launch would expose unknown Meta, language, operator, and fulfillment failures at once. | Medium | All prior table stakes; production number; test customers; go/no-go owner | Recommended gate: at least 7 consecutive pilot days, 5 selected customers, and 20 production-like order lifecycles; zero duplicate orders, zero restricted autonomous actions, zero known critical defects, 100% handoffs visible to the owner, successful restore/rollback drills, and owner completion of daily operations without developer intervention. |

## Differentiators

These are not required to make the first pilot safe, but they materially improve trust,
operability, or learning without expanding the product surface.

| Capability | Value Proposition | Complexity | Dependencies | Measurable Acceptance Implication |
|------------|-------------------|------------|--------------|-----------------------------------|
| Risk-tiered autonomy | Uses deterministic rules to distinguish low-risk ordering from high-risk ambiguity, reducing unnecessary handoffs without broadening authority. | High | Action allowlist; handoff; evals; event taxonomy | Every intent/action maps to a documented risk tier; autonomy can be disabled by tier; pilot reports autonomous success and false-handoff rates separately. |
| Customer-visible change receipt | Shows exactly what changed in a `to_do` order, new total, and current status, reducing disputes. | Medium | Atomic order changes; audit events; message templates | Every successful change sends before/after line differences and total; customer confirmation links to the same audit event; owner sees delivery status. |
| Replayable decision evidence | Reconstructs the input, policy decision, tool result, and final outcome without allowing a replay to repeat side effects. | High | Correlation IDs; redacted snapshots; idempotency; versioning | A sampled incident can be reconstructed end-to-end in under 10 minutes; replay defaults to dry-run; sensitive fields remain redacted. |
| Shadow-mode evaluation before autonomy changes | New prompts/models can score real anonymized traffic without controlling production. | High | Anonymization; evaluation runner; prompt versioning | Candidate behavior runs on a representative sample; differences are reviewed; no autonomy expansion ships solely on offline synthetic cases. |
| Policy-aware messaging planner | Selects service text versus the correct approved template from consent, message category, and service-window state. | Medium | Consent ledger; template registry; last-user-message clock | Planner has deterministic tests around the 24-hour boundary; missing/paused templates create operator work instead of sending noncompliant text. |
| Cost and quality dashboard for one owner | Converts provider metrics into plain-language daily health: conversations, cost, failures, handoffs, and unusual spend. | Medium | Usage/cost capture; eval outcomes; alerts | Owner can identify today's spend, top failure cause, oldest handoff, and whether automation is healthy from one page; cost reconciliation matches provider reporting within an agreed tolerance. |
| Privacy operations report | Proves that retention, anonymization, and redaction actually run. | Medium | Data inventory; retention jobs; audit events | Monthly report shows records expired, anonymized, failed, and manually exempted; failures become work-queue items. |
| Cutover readiness dashboard | Makes go/no-go evidence explicit instead of relying on memory. | Low | Acceptance checks; monitoring; pilot metrics | Launch checklist shows owner sign-off, Meta status, template approvals, eval gate, restore/rollback evidence, open severity-1/2 defects, and pilot metrics; any red gate blocks cutover. |

## Anti-Features

These capabilities should explicitly not be built for this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| General-purpose WhatsApp assistant | Increases policy exposure, prompt-injection surface, cost, and unsupported commitments; it is unrelated to the business ordering purpose. | Keep the agent narrowly scoped to catalog, store policy, ordering, and order support; hand off unrelated requests. |
| Medical diagnosis, treatment advice, or reaction assessment | Skincare questions can become health-sensitive, and Meta places restrictions on medical/healthcare commerce and information. | Provide only approved cosmetic usage information; route possible reactions and medical questions to a human with an emergency disclaimer where appropriate. |
| Autonomous refunds, discounts, price changes, substitutions, or goodwill promises | These are financially consequential and easy for an AI to overcommit. | Create a handoff with a proposed summary; only the owner approves and records the decision. |
| Automatic order edits after `to_do` | Fulfillment may already have started, so edits can create inventory, delivery, and invoice mismatches. | Lock automated mutation and open a handoff; owner decides the operational remedy. |
| Hard deletion of orders or audit history | Removes evidence needed for reconciliation, disputes, and debugging. | Use status changes, tombstones where required, and separately controlled retention/anonymization. |
| Unlimited retries or recursive agent loops | Causes duplicate side effects, customer spam, runaway cost, and retry storms during outages. | Use bounded, classified retries with backoff, idempotency, dead-letter/operator queues, and hard per-turn limits. |
| Fail-open AI behavior | Invented answers during provider or database failures are worse than a short delay. | Use deterministic fallback text and human handoff; fail closed for mutations. |
| Automated replies while a human owns the conversation | The bot can contradict the owner or compound an angry, sensitive, or medical case. | Persist an automation-paused state until explicit resume/resolve. |
| Broadcasts based only on order history | Purchase history does not by itself prove permission for marketing messages, and Meta requires opt-in and opt-out handling. | Maintain category-specific consent and suppress opted-out users; use approved templates when initiating. |
| Raw transcripts, secrets, or identifiers in logs | Operational logs are widely copied and retained; message content and credentials create unnecessary breach impact. | Log structured metadata, event IDs, redacted excerpts only when necessary, and protected audit references. |
| Indefinite conversation retention | "Keep everything for AI improvement" conflicts with minimization and the project's 12-month policy. | Anonymize on schedule; retain only labeled, de-identified evaluation cases with provenance and review. |
| Homegrown cryptography or static shared admin cookies | The existing SHA-256 password/session pattern is difficult to secure and recover safely. | Use a managed or well-reviewed authentication/session implementation with MFA and standard password hashing. |
| Microservices, event streaming, or multi-tenant administration | At 10-30 orders/day and one operator, operational complexity would exceed the reliability benefit. | Keep the modular monolith; add durable boundaries, idempotency, outbox/retry records, and observability. |
| Integrated payments, courier automation, loyalty programs, or a public website | These are new product expansions and introduce regulatory, security, and support scope that does not unblock safe launch. | Keep cash/manual payment and owner-managed fulfillment; plan later milestones separately. |
| Unrestricted day-one public launch | Masks operator and integration defects until many customers are affected. | Use internal testing, owner-only operation, selected-customer pilot, then controlled cutover with rollback criteria. |

## Feature Dependencies

```text
Production schema + constraints
    -> idempotency + state machine + append-only audit
    -> safe confirmation/change/cancellation

Managed authentication + secure sessions
    -> authorized dashboard mutations
    -> operator inbox + incident controls

Meta onboarding + production number + TLS
    -> signed real-envelope webhook handling
    -> message/status/policy webhooks

Consent ledger + approved template registry + service-window clock
    -> compliant delayed order updates, follow-ups, broadcasts, and owner reports

Server-side AI action policy + deterministic fallbacks
    -> human handoff and pause semantics
    -> representative eval release gate
    -> controlled pilot

Structured events + external monitoring + runbooks
    -> incident detection and containment
    -> rollback/restore drills
    -> public cutover
```

## Acceptance Scorecard

The following recommended thresholds turn the feature list into a launch decision. They are
product recommendations, not vendor-mandated values, and should be confirmed with the owner
during phase planning.

| Area | Pilot Gate | Public Cutover Gate |
|------|------------|----------------------|
| Duplicate safety | 10x replay and concurrent-confirm tests create one logical outcome | Zero duplicate orders or duplicate autonomous changes during pilot |
| Restricted actions | 100% refusal/handoff on the critical safety eval set | Zero restricted autonomous actions in pilot |
| Ordinary ordering | >= 95% correct state and tool side effects on representative evals | >= 95% successful ordinary production-like order lifecycles, with failures safely handed off |
| Handoff | 100% trigger coverage for designated categories; pause invariant passes | 100% handoffs visible; no automated messages while paused; owner resolves without database access |
| Order changes | All `to_do` change/cancel and concurrency tests pass | Zero unauthorized late-status mutations |
| Messaging compliance | Consent, template, opt-out, and 24-hour boundary tests pass | All initiated pilot messages have recorded consent basis and approved template where required |
| Security | No known critical/high exploitable dashboard, webhook, secret, or database access defect | MFA active; external scan and negative auth/CSRF tests pass |
| Privacy | Retention/redaction dry-run produces expected report | Published notice; deletion/anonymization job succeeds with no unexplained failures |
| Recovery | Backup restore and reconciliation pass within targets | Rollback and automation kill-switch drills pass |
| Operations | Alerts and work queue are verified with injected failures | 7-day pilot; owner completes daily opening, exception handling, and closing workflows independently |

## MVP Recommendation

Prioritize in this order:

1. **Prevent irreversible harm and duplicate side effects**
   - Production schema, constraints, signed webhook parsing, idempotency, state machine, safe
     `to_do` changes/cancellation, and server-side AI action restrictions.
2. **Give the owner control over exceptions**
   - Human handoff with automation pause, needs-attention queue, secure authentication, audit
     history, and kill switches.
3. **Make all messaging policy-compliant**
   - Opt-in evidence, opt-out suppression, approved templates, 24-hour window logic, delivery
     errors, quality/policy webhooks, and skincare claims review.
4. **Prove reliability under failure**
   - AI fallbacks, eval release gates, cost caps, external monitoring, retention jobs,
     backup/restore, incident runbooks, and rollback.
5. **Pilot before cutover**
   - Production-number end-to-end tests, owner training, selected-customer pilot, measurable
     go/no-go review, and controlled public enablement.

Defer the differentiators until table-stakes gates pass. The best early differentiator is the
cutover readiness dashboard because it is low complexity and helps a nontechnical owner
understand whether launch is actually safe.

## Key Findings

1. The existing 3-day follow-up workflow and arbitrary broadcasts conflict with current Meta
   requirements unless they use approved templates, recorded opt-in, and opt-out suppression.
2. Human handoff is not optional polish. Meta's current policy explicitly requires prompt,
   clear, direct escalation paths when automation is used.
3. Idempotency must cover the complete business effect, not only HTTP response handling:
   inbound message, cart/order mutation, notification, customer reply, retry, and audit event.
4. Order modification is a concurrency problem. A simple pre-check for `to_do` is insufficient;
   the state check and mutation must be atomic.
5. For a one-owner business, an operator work queue and kill switches provide more launch value
   than sophisticated autonomous behavior.
6. A blanket bot p95 target below two seconds is unsuitable for live AI and external APIs.
   Keep the existing target for deterministic commands and define a separate measured AI
   latency budget.
7. Skincare remains a valid narrow commerce use case only if catalog and agent language avoid
   unsupported medical/healthcare classification and advice.

## Sources

Primary and official sources were preferred for changing platform facts.

- **HIGH confidence:** [WhatsApp Business Messaging Policy](https://whatsappbusiness.com/policy/)
  - Current policy on opt-in, opt-out, approved templates, the 24-hour service window, required
    escalation paths for automation, privacy notices, sensitive identifiers, enforcement, and
    commerce restrictions. Accessed 2026-06-14.
- **HIGH confidence:** [Meta WhatsApp Business Platform Webhooks](https://developers.facebook.com/docs/whatsapp/webhooks)
  - Current official Cloud API envelope, message IDs, status/error events, WABA events, and
    HTTPS/TLS requirements. Accessed 2026-06-14.
- **HIGH confidence:** [Meta official WhatsApp webhook signature-validation sample](https://github.com/fbsamples/whatsapp-api-examples/tree/main/signature-validation-with-webhooks-payloads)
  - Official example validating `X-Hub-Signature-256` over the raw payload. Accessed 2026-06-14.
- **HIGH confidence:** [Meta WhatsApp policy enforcement](https://developers.facebook.com/docs/whatsapp/overview/policy-enforcement)
  - Restriction behavior, Business Support Home, admin notifications, and `account_update`
    webhook guidance. Accessed 2026-06-14.
- **HIGH confidence:** [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
  - RLS expectations for exposed schemas and service-key bypass risk. Accessed 2026-06-14.
- **HIGH confidence:** [Supabase Database Backups](https://supabase.com/docs/guides/platform/backups)
  - Backup/restore behavior, downtime, PITR, and Storage-object limitation. Accessed 2026-06-14.
- **HIGH confidence:** [Anthropic: Define success criteria and build evaluations](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests)
  - Task-specific, multidimensional, edge-case evaluation guidance. Accessed 2026-06-14.
- **HIGH confidence:** [Anthropic API rate limits](https://platform.claude.com/docs/en/api/rate-limits)
  - Spend limits, workspace limits, 429/retry headers, and rate-limit monitoring. Accessed
    2026-06-14.
- **HIGH confidence:** [Anthropic Usage and Cost API](https://platform.claude.com/docs/en/manage-claude/usage-cost-api)
  - Programmatic token/cost monitoring and budget-alert use cases. Accessed 2026-06-14.
- **HIGH confidence:** [Anthropic API errors](https://platform.claude.com/docs/en/api/errors)
  - Typed errors and provider request IDs for support correlation. Accessed 2026-06-14.
- **HIGH confidence:** [Anthropic API and data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention)
  - Current API retention arrangements and the need to verify feature/model-specific handling.
    Accessed 2026-06-14.
- **HIGH confidence:** [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
  [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
  [CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html),
  and [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
  - Authentication, MFA, login throttling, cookie/session expiration, CSRF, logging, and
    de-identification guidance. Accessed 2026-06-14.
- **HIGH confidence:** [NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final)
  - Current incident response preparation, detection, response, and recovery guidance,
    published April 2025. Accessed 2026-06-14.
- **HIGH confidence project evidence:** `.planning/PROJECT.md`,
  `.planning/intel/requirements.md`, `.planning/codebase/CONCERNS.md`, and
  `.planning/codebase/TESTING.md`.

## Research Gaps

- Applicable privacy, consumer-protection, tax, and accounting retention law depends on the
  business's legal entity, customer locations, and operating jurisdiction. The engineering
  retention design can proceed, but the final privacy notice and order/invoice retention period
  need local legal/accounting confirmation.
- The exact Meta product classification of every skincare item and claim requires review of
  the real catalog and current Commerce Policy in the business account.
- Numeric pilot thresholds are recommended starting points. Phase planning should confirm
  acceptable response times, recovery targets, business hours, and monthly AI budget with the
  owner.
