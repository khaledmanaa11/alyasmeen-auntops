# Requirements - ALYASMEEN AuntOps Production Readiness

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| **Supabase (M1)** | | |
| REQ-prod-atomic-orders | Phase 1 | Pending |
| REQ-prod-backup-restore | Phase 1 | Pending |
| REQ-prod-migrations | Phase 1 | Pending |
| REQ-nfr-data | Phase 1 | Pending |
| REQ-bot-session-persist | Phase 1 | Pending |
| **FastAPI (M2)** | | |
| REQ-bot-webhook | Phase 2 | Pending |
| REQ-prod-raw-hmac | Phase 2 | Pending |
| REQ-prod-inbox | Phase 2 | Pending |
| REQ-prod-outbox | Phase 2 | Pending |
| REQ-prod-idempotency | Phase 2 | Pending |
| REQ-prod-struct-log | Phase 2 | Pending |
| REQ-prod-metrics | Phase 2 | Pending |
| REQ-prod-cicd | Phase 2 | Pending |
| REQ-prod-pinned-model | Phase 2 | Pending |
| REQ-nfr-latency | Phase 2 | Pending |
| REQ-nfr-uptime | Phase 2 | Pending |
| **Agent (M3)** | | |
| REQ-prod-policy-gate | Phase 3 | Pending |
| REQ-prod-handoff (Logic) | Phase 3 | Pending |
| REQ-prod-eval-gate | Phase 3 | Pending |
| REQ-bot-ai-fallback | Phase 3 | Pending |
| REQ-ai-no-hallucination | Phase 3 | Pending |
| REQ-ai-tools | Phase 3 | Pending |
| REQ-bot-aunt-notification | Phase 3 | Pending |
| REQ-sched-followup | Phase 3 | Pending |
| REQ-sched-retry-queue | Phase 3 | Pending |
| **UI (M4)** | | |
| REQ-prod-auth-mfa | Phase 4 | Pending |
| REQ-prod-session-opaque | Phase 4 | Pending |
| REQ-prod-csrf | Phase 4 | Pending |
| REQ-prod-sec-headers | Phase 4 | Pending |
| REQ-prod-handoff (UI) | Phase 4 | Pending |
| REQ-dash-login | Phase 4 | Pending |
| REQ-dash-orders-list | Phase 4 | Pending |
| REQ-dash-orders-filter | Phase 4 | Pending |
| REQ-dash-status-update | Phase 4 | Pending |
| REQ-dash-products-crud | Phase 4 | Pending |
| **Go-Live (M5)** | | |
| REQ-nfr-test-coverage | Phase 5 | Pending |
| Meta WABA Finalization | Phase 5 | Pending |
| Staged Pilot | Phase 5 | Pending |
| Operator Training | Phase 5 | Pending |

## Detail

### Production Readiness Requirements

#### Reliability and Idempotency
- **REQ-prod-inbox**: Durable Webhook Inbox persistence before response (M2).
- **REQ-prod-outbox**: Durable Outbox for messages and side effects (M2).
- **REQ-prod-atomic-orders**: Atomic transaction for order creation and status transitions (M1).
- **REQ-prod-idempotency**: Every side effect must have a stable idempotency key (M2).

#### Security
- **REQ-prod-auth-mfa**: Replace shared password with Supabase Auth + TOTP MFA (M4).
- **REQ-prod-session-opaque**: Use opaque server-side sessions, not client-side signed cookies (M4).
- **REQ-prod-csrf**: Implement CSRF protection for all mutating dashboard routes (M4).
- **REQ-prod-sec-headers**: Add CSP, HSTS, and other security headers (M4).
- **REQ-prod-raw-hmac**: Verify Meta X-Hub-Signature-256 over raw request body (M2).

#### AI Governance
- **REQ-prod-policy-gate**: Deterministic application policy validates all AI-proposed actions (M3).
- **REQ-prod-pinned-model**: Use pinned model snapshots instead of floating aliases (M2).
- **REQ-prod-handoff**: Explicit human-handoff state and operator inbox (M3, M4).
- **REQ-prod-eval-gate**: Pytest-based evaluation release gates for model behavior (M3).

#### Observability and Operations
- **REQ-prod-struct-log**: JSON structured logging with correlation IDs (M2).
- **REQ-prod-metrics**: Application-level metrics (latency, error rates, cost) and alerts (M2).
- **REQ-prod-backup-restore**: Automated off-site backups and quarterly restore drills (M1).
- **REQ-prod-migrations**: Versioned Supabase CLI migrations; no direct dashboard edits (M1).
- **REQ-prod-cicd**: GitHub Actions for CI/CD with release approvals and rollback (M2).

### Functional Requirements (Legacy/Core)

#### WhatsApp Bot
- **REQ-bot-webhook**: Receive incoming WhatsApp messages via Meta Cloud API webhook.
- **REQ-bot-hard-commands**: Handle hard commands: `cart`, `clear`, `menu`, etc.
- **REQ-bot-order-tracking**: Handle Arabic order tracking.
- **REQ-bot-session-persist**: Persist cart/stage/address in Supabase.
- **REQ-bot-confirm-flow**: On `confirm`: write order + lines, send confirmation.
- **REQ-bot-aunt-notification**: Aunt new-order alert reliability.

#### AI Conversation
- **REQ-ai-persona**: System prompt positions AI as "عمة ALYASMEEN".
- **REQ-ai-no-hallucination**: Suggest only Supabase-catalog products.
- **REQ-ai-tools**: Provide reliable tools: `add_to_cart`, `show_menu`, etc.
- **REQ-ai-nl-mutations**: NL intents cause real cart/session mutations.

#### Web Dashboard
- **REQ-dash-login**: Secure operator login.
- **REQ-dash-orders-list**: Orders management.
- **REQ-dash-status-update**: Status update + customer notification.
- **REQ-dash-products-crud**: Catalog management.
- **REQ-dash-pdf-invoice**: Automatic PDF invoice generation.

#### Background Scheduler
- **REQ-sched-followup**: Automatic customer follow-ups.
- **REQ-sched-monthly-report**: Monthly business summary to aunt.
- **REQ-sched-retry-queue**: Reliable processing of retry queue.
