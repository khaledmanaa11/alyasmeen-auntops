# Domain Pitfalls

**Domain:** Productionizing an existing WhatsApp commerce agent  
**Project:** ALYASMEEN AuntOps Production Readiness  
**Researched:** 2026-06-14  
**Overall confidence:** HIGH for project-specific findings and documented platform behavior; MEDIUM for Meta review timing because approval outcomes are account-specific

## Critical Warnings

1. **Meta onboarding is already on the critical path.** The real number, WABA subscription, two-step PIN, access token, display name, and approved templates must work before the rest of the system can prove production readiness. Do not defer this to M5.
2. **The current webhook cannot process real Meta envelopes.** It expects a flat development payload, performs no POST signature check, and runs database, AI, and outbound messaging work synchronously before acknowledging the webhook.
3. **Order creation is neither idempotent nor atomic.** A duplicate `confirm` event can create duplicate orders, while an interrupted multi-call insert can create an order with missing lines.
4. **Outbound WhatsApp failures are largely invisible.** `send_text()` returns non-2xx responses instead of raising, while callers frequently treat "no exception" as success. The existing retry queue therefore does not reliably receive failed sends.
5. **Supabase access may be effectively unrestricted.** All application SQL is passed as text through custom `run_query` and `run_exec` RPC functions. Their ownership, grants, `SECURITY DEFINER` behavior, `search_path`, and key usage are production blockers until audited.
6. **The AI is currently allowed to make unsafe guesses.** Its prompt says to choose the closest product when ambiguous and exposes mutating tools without a complete policy gate, handoff state, strict validation, or transaction boundary.
7. **The dashboard session is a permanent shared bearer token.** It has no expiry, server-side revocation, CSRF token, login throttling, or secure-cookie enforcement.
8. **In-process scheduled jobs will duplicate when the web service scales.** Every worker starts APScheduler, and the retry processor does not claim rows with a lock or lease.
9. **A one-month deadline makes scope discipline a safety control.** Public launch must be blocked unless the staged pilot, restore drill, rollback drill, operator training, and incident response evidence are complete.

## Milestone Ownership

| Milestone | Must Prevent |
|-----------|--------------|
| **M1: Supabase to Production** | Excessive database privilege, schema drift, partial writes, missing constraints, untested backup restoration, and unimplemented retention |
| **M2: FastAPI to Production** | Invalid or forged webhooks, lost/duplicate events, unsafe retries, development configuration in production, broken deployment health checks, and unexercised rollback |
| **M3: Agent to Production** | Hallucinated commitments, unsafe tool calls, prompt injection, medical advice, automation during handoff, uncontrolled cost/latency, and weak evaluation coverage |
| **M4: UI to Production** | Shared permanent sessions, brute-force login, CSRF, missing authorization, unsafe broadcasts, and an operator UI that hides failures |
| **M5: Go-Live** | Unverified Meta assets, untested full lifecycle, absent monitoring, untrained operator, uncontrolled cutover, and launch under unresolved critical defects |

## Critical Pitfalls

### Pitfall 1: Meta WABA Onboarding Becomes the Launch Blocker

**What goes wrong:** The code is ready for a pilot, but the real number cannot send or receive because the business portfolio, WABA, phone ownership, display name, app subscription, token permissions, or two-step registration state is incomplete.

**Why it happens:** Meta setup spans several assets with different IDs and approval states. The official Meta Postman collection states that a business portfolio, WABA, and business phone number are required; the app must be subscribed to the WABA; registration sets a six-digit two-step PIN; and an Embedded Signup number must be registered within 14 days or repeat signup. User tokens expire quickly, so a production system must not depend on a temporary test token.

**Consequences:** M5 cannot start, scheduled work is compressed into the final days, and the team may weaken security or skip the pilot to meet the date.

**Warning signs:**
- The production phone number ID, WABA ID, business portfolio ID, and app ID are not recorded in one controlled runbook.
- `GET /{WABA-ID}/phone_numbers` does not show the expected number and approved display name.
- `POST /{WABA-ID}/subscribed_apps` has not been verified.
- A test message works only with a temporary token or Meta test number.
- The two-step PIN owner and recovery procedure are unknown.
- The real-number problem has no Meta support case number, owner, next action, or escalation date.

**Prevention:**
- Treat onboarding as a parallel workstream beginning immediately, owned by one named person with a daily status check.
- Record asset IDs, permissions, display-name status, number status, template status, support case, and blockers without storing secret token values in the runbook.
- Create a system-user token with only required WhatsApp permissions and test its validity from production configuration.
- Verify number registration, WABA subscription, inbound webhook delivery, and outbound send using the real number before M2 closes.
- Preserve the two-step PIN and recovery codes in an owner-controlled password manager.

**Verification evidence:**
- Screenshots or API output showing the expected WABA and registered phone number.
- Successful WABA subscription response.
- Successful inbound message and outbound reply on the real number with message IDs captured.
- Token debugger output showing required permissions and expected expiry behavior.
- At least one approved Arabic template and one approved English template sent successfully.

**Contingency/rollback:**
- If registration is not operational by the M2 exit gate, replan M5 rather than launching on the test number.
- Keep the aunt's existing manual WhatsApp ordering process as the business continuity path.
- Use a Business Solution Provider only if the direct Cloud API path remains blocked and the cost, data handling, number migration, and exit process are explicitly accepted.

**Milestone mapping:** Start now; M2 must prove the real transport; M5 is blocked without final asset and template verification.  
**Confidence:** HIGH for required assets and registration mechanics; MEDIUM for review/support timing.

### Pitfall 2: Templates and Messaging Policy Fail Outside the Service Window

**What goes wrong:** Order reminders, follow-ups, monthly outreach, status updates, or broadcasts work in development but are rejected for customers who have not recently messaged the business.

**Why it happens:** Business-initiated WhatsApp messages outside the customer-service window require approved templates in the correct language and category. The current broadcast and scheduled-job code sends free-form text, does not select a template, and treats many API error responses as successful sends.

**Consequences:** Customers miss order updates, follow-ups silently fail, broadcasts violate policy expectations, or the number's quality is harmed by unwanted messaging.

**Warning signs:**
- No inventory maps each outbound use case to free-form service reply or approved template.
- Templates remain `PENDING`, `REJECTED`, `PAUSED`, or language-mismatched.
- Broadcast recipients include every customer without consent or opt-out state.
- The dashboard reports `sent` when Meta returned a non-2xx response.
- Template delivery is tested only with the Meta `hello_world` sample.

**Prevention:**
- Define the minimum template set during M2: order ready, delivery update, completion/invoice, human follow-up, and any permitted marketing message.
- Submit Arabic and English variants early and keep wording stable during review.
- Store customer language, marketing consent, opt-out status, last inbound timestamp, template name/version, and send result.
- Separate transactional templates from marketing broadcasts.
- Disable unrestricted "send to all" until consent and approved-template rules are enforced.

**Verification evidence:**
- Template inventory with approved status, language, category, variables, and owner.
- Automated tests choosing template versus free-form message based on last inbound time.
- Real-number sends to pilot recipients inside and outside the service window.
- Delivery-status webhook records and explicit non-2xx failure tests.
- Opt-out request test proving future marketing sends are blocked.

**Contingency/rollback:**
- Fall back to aunt-managed replies for recipients who cannot legally or technically receive an automated message.
- Disable broadcasts while retaining order operations.
- If a template is paused or rejected, switch to an already approved minimal transactional template rather than editing production behavior ad hoc.

**Milestone mapping:** M2 owns transport and template integration; M4 owns consent-safe broadcast controls; M5 validates real sends.  
**Confidence:** HIGH.

### Pitfall 3: Webhooks Are Rejected, Forged, Timed Out, or Silently Lost

**What goes wrong:** Real messages return 422, forged requests trigger database and Claude work, legitimate events time out, or an exception is converted to HTTP 200 and is never retried.

**Why it happens:** `webhook_post()` accepts only `Msg(from_number, text, wa_name)` rather than Meta's `entry[].changes[].value.messages[]` envelope. It does not read raw bytes or call the existing signature verifier. It also performs database access, AI calls, order creation, and outbound sends before returning. The global exception handler returns HTTP 200 with an error body for all `/whatsapp/` exceptions.

**Consequences:** Complete production outage, unauthorized order creation and AI spend, duplicate processing after timeouts, or silent inbound-message loss.

**Warning signs:**
- Real Meta fixture tests are absent or still produce 422.
- Requests without `X-Hub-Signature-256` are accepted.
- Webhook latency includes Claude API latency.
- Error logs increase while webhook HTTP status remains 200.
- Status events, interactive replies, media messages, or multiple entries crash parsing.
- No durable inbound event row exists before acknowledgement.

**Prevention:**
- Verify the HMAC over the exact raw request bytes before parsing; fail closed when the app secret is absent in production.
- Parse the full envelope and safely ignore unsupported changes while recording their type.
- Store each inbound event durably using Meta's message/event identifier, then acknowledge quickly.
- Move AI and outbound reply processing behind the durable inbox boundary.
- Return 2xx only when the event is authenticated and durably accepted; use non-2xx for transient acceptance failures.
- Remove exception details from customer-facing responses.

**Verification evidence:**
- Contract tests using captured, redacted Meta text, interactive, status, malformed, multi-message, and media envelopes.
- Signature tests for valid body, changed body, missing header, wrong secret, and secret-not-configured startup failure.
- Load/latency test proving acknowledgement remains below the chosen internal budget while Claude is slow or unavailable.
- Replay test proving the same event ID is accepted once and processed once.
- Production-like test proving a database outage produces an alert and a retryable response, not a false 200.

**Contingency/rollback:**
- Feature-flag automated processing off while leaving authenticated inbound capture on.
- Route captured events to a dashboard inbox for manual reply.
- Roll back to the previous app image only if the database inbox schema remains backward compatible.

**Milestone mapping:** M2 launch blocker; M5 repeats the tests on the real callback URL.  
**Confidence:** HIGH.

### Pitfall 4: Duplicate Events and Partial Writes Create Duplicate or Corrupt Orders

**What goes wrong:** A replayed `confirm` creates two orders, a network interruption leaves an order without lines, or retries send duplicate customer notifications.

**Why it happens:** Order creation performs separate RPC writes for order insert, order name, and each line. There is no transaction, inbound-event uniqueness constraint, confirmation idempotency key, or outbox. The database layer correctly avoids blind write retries, but that means uncertain write outcomes are not resolved automatically.

**Consequences:** Double fulfillment, wrong revenue, customer disputes, missing invoice lines, and manual reconciliation.

**Warning signs:**
- Two orders for the same phone, cart, and minute.
- Orders with zero lines or totals that do not equal line totals.
- Duplicate WhatsApp message IDs for the same business event.
- Retrying a failed request requires guessing whether the write committed.
- Status notifications are sent before or independently of the status transaction.

**Prevention:**
- Add an `inbound_events` table with a unique Meta event/message ID and processing state.
- Create orders and lines in one database transaction or one narrowly scoped RPC function with typed parameters.
- Persist a stable confirmation idempotency key and enforce uniqueness.
- Add an outbox table for notifications; make each outbox action unique by business event.
- Add constraints for valid statuses, positive quantities/prices, required delivery address, and order total consistency where practical.
- Make status transitions compare-and-set from allowed prior states.

**Verification evidence:**
- Concurrent replay test posts the same confirmation many times and produces one order, one set of lines, and one notification intent.
- Fault-injection tests interrupt after each write boundary and prove rollback or safe resumption.
- Database queries show no zero-line orders and no duplicate idempotency keys.
- Reconciliation report compares order totals, lines, and outbound events.

**Contingency/rollback:**
- Stop automated fulfillment and place suspicious orders in a reconciliation queue.
- Provide an operator action to mark a duplicate without deleting audit evidence.
- Re-send notifications from the outbox only after verifying the business event state.

**Milestone mapping:** M1 owns transaction and constraints; M2 owns webhook idempotency and outbox processing; M5 validates reconciliation.  
**Confidence:** HIGH.

### Pitfall 5: Supabase RPC Privilege Bypasses Least Privilege and RLS

**What goes wrong:** Possession of the configured Supabase key allows arbitrary SQL through `run_query(sql)` or `run_exec(sql)`, or a `SECURITY DEFINER` function executes with excessive rights and an unsafe `search_path`.

**Why it happens:** The application sends complete SQL strings through generic RPC functions. RLS protection depends on the function definitions, owner, grants, key role, and whether the function bypasses table policies. These details are not captured in `schema.sql`.

**Consequences:** Full customer/order disclosure, destructive writes, privilege escalation, and an unrecoverable breach if the key leaks.

**Warning signs:**
- `anon` or `authenticated` can execute the generic SQL RPCs.
- The Railway service uses a browser-safe anon key for privileged backend writes without explicit policies.
- The service role key appears in client JavaScript, logs, screenshots, or repository history.
- RLS is disabled on public-schema tables created through SQL.
- Function definitions are managed manually in the Supabase dashboard and absent from migrations.

**Prevention:**
- Export and review the exact function definitions, ownership, grants, volatility, and `search_path`.
- Revoke generic RPC execution from `anon` and `authenticated`.
- Prefer narrowly scoped RPCs or direct parameterized database access; if generic RPCs remain temporarily, isolate them to a dedicated least-privilege role available only to the server.
- Enable and test RLS on all exposed public-schema tables even when backend access normally bypasses it.
- Rotate keys after the audit and whenever accidental exposure is suspected.

**Verification evidence:**
- Migration files recreate roles, functions, grants, RLS, and policies from an empty database.
- pgTAP or equivalent tests prove anonymous and authenticated clients cannot read or mutate operational tables.
- Security Advisor has no unresolved critical findings.
- Secret scan confirms privileged keys are absent from repository and frontend assets.
- A privilege matrix identifies which runtime identity can execute each function.

**Contingency/rollback:**
- Immediately revoke the affected key/function grant and rotate credentials.
- Put the app in manual-order mode if database write access must be suspended.
- Restore or reconcile from audit data if unauthorized writes occurred.

**Milestone mapping:** M1 absolute blocker; M5 rechecks deployed key and policy state.  
**Confidence:** HIGH.

### Pitfall 6: Schema Drift and Unsafe Migrations Break Fresh Deployments

**What goes wrong:** Production contains dashboard-created objects that the repository cannot reproduce, a fresh database lacks `monthly_snapshots`, or a deployment applies code before its required schema.

**Why it happens:** `app/db/schema.sql` is a rerunnable snapshot, not ordered migrations. The current code already queries a missing table. Supabase warns that direct remote edits bypass migration history and cause future `db push` synchronization errors.

**Consequences:** Production-only failures, inability to create staging, risky manual fixes, and rollback incompatibility.

**Warning signs:**
- `supabase migration list` differs between local and remote.
- A clean `supabase db reset` cannot run the full test suite.
- SQL editor changes are not represented in Git.
- New code requires a column/table that old code cannot tolerate.
- Rollback restores old code against a schema it cannot understand.

**Prevention:**
- Baseline the actual remote schema into versioned migrations, including RPC functions, grants, RLS, indexes, constraints, and `monthly_snapshots`.
- Stop direct production schema edits after baselining.
- Use expand-contract migrations: add compatible objects first, deploy code second, remove obsolete objects only later.
- Run migration dry-run/status checks in CI and designate one deployment path.
- Add schema smoke tests for every table and function the app queries.

**Verification evidence:**
- Empty local database rebuilt solely from migrations.
- Staging upgraded from the current production baseline and tested.
- Migration history matches Git and the linked project.
- Forward and rollback compatibility matrix is documented for each release.
- Monthly-report and dashboard snapshot tests pass on the rebuilt database.

**Contingency/rollback:**
- Prefer a forward-fix migration for additive errors.
- Roll back code only when the migration was backward compatible.
- For destructive migration failure, stop writes, restore to a separate recovery project, validate data, and execute the documented cutover.

**Milestone mapping:** M1 launch blocker; M2 deployment pipeline must apply migrations once; M5 exercises the procedure.  
**Confidence:** HIGH.

### Pitfall 7: Backups Exist but Recovery Does Not

**What goes wrong:** The team assumes Supabase backups are sufficient, but the plan tier, retention, download availability, restore downtime, credentials, and application reconciliation steps are unknown.

**Why it happens:** Backup presence is confused with recoverability. Supabase documents plan-dependent backup behavior and notes that the project is unavailable during a point-in-time restore.

**Consequences:** Extended outage, excessive data loss, or destructive experimentation on the only production project.

**Warning signs:**
- No explicit recovery point objective (RPO) or recovery time objective (RTO).
- No dated restore drill with measured duration and record counts.
- The owner alone has access to initiate recovery.
- A restore has never been tested against current migrations and application code.
- Retention claims do not account for personal data remaining in backups.

**Prevention:**
- Select a plan and backup method that meet the business RPO/RTO.
- Add an independent logical export procedure for critical tables when appropriate.
- Restore into an isolated recovery project for drills where the platform permits.
- Document post-restore checks: schema version, row counts, recent orders, idempotency state, outbox/retry state, and webhook configuration.
- Protect Supabase owner accounts with MFA and maintain a second trusted owner.

**Verification evidence:**
- Successful restore drill with start/end time, restored timestamp, row-count comparison, and app smoke test.
- Recorded RPO/RTO accepted by the owner.
- Recovery credentials and escalation contacts verified.
- Evidence that retention/anonymization procedures address active data and backup limitations.

**Contingency/rollback:**
- Freeze incoming writes and switch to manual WhatsApp order capture.
- Restore to an isolated project, verify, then update the application connection only through the cutover checklist.
- Reconcile orders received during downtime from the manual log and WhatsApp conversation history.

**Milestone mapping:** M1 must prove restoration; M5 repeats a tabletop or technical disaster-recovery drill.  
**Confidence:** HIGH.

### Pitfall 8: Production Configuration or Deployment Starts in an Unsafe State

**What goes wrong:** Production boots with mock WhatsApp enabled, weak default secrets, missing app secret, debug endpoints, obsolete Graph API version, no readiness check, or an untested dependency combination.

**Why it happens:** `USE_MOCK_WHATSAPP` defaults to true; dashboard secrets have known defaults; the app secret is optional; debug routes are always registered; dependencies use broad lower bounds; and `/` is only a static response. The app also uses deprecated FastAPI startup/shutdown events.

**Consequences:** Customers receive no real replies, attackers access development functions, deployments look healthy while Supabase is unavailable, or a package update breaks the release.

**Warning signs:**
- Startup succeeds with a missing production secret.
- `/dev/*` exists on the production domain.
- Health check passes while `ping()` fails.
- The runtime Graph API endpoint is still hard-coded to `v19.0` without a live support check.
- Rebuilding the same commit installs different dependency versions.
- Railway rollback has never been exercised with current variables.

**Prevention:**
- Add a production startup validator that rejects mock mode, weak/default secrets, missing Meta/Claude/Supabase credentials, unsupported API configuration, and debug routes.
- Pin or lock resolved production dependencies.
- Add separate liveness and readiness endpoints; readiness should verify required configuration and a bounded Supabase check.
- Use FastAPI lifespan for startup/shutdown ownership.
- Configure Railway health checks, restart policy, and a single pre-deploy migration command.
- Verify a currently supported Graph API version and keep it configurable.
- Maintain backward-compatible schema changes so Railway image rollback remains useful.

**Verification evidence:**
- Negative startup tests for every missing or default secret.
- Production route inventory excludes debug endpoints and internal exception details.
- Health tests prove liveness and readiness fail for different reasons.
- Clean build from lock file and dependency vulnerability scan.
- Railway rollback drill restores the previous image and variables, followed by smoke tests.

**Contingency/rollback:**
- Disable public traffic or webhook subscription if unsafe configuration is detected.
- Roll back to the previous successful Railway deployment.
- Keep the database on the forward-compatible schema and issue a forward fix if code rollback is unsafe.

**Milestone mapping:** M2 owns prevention; M5 owns deployment and rollback drills.  
**Confidence:** HIGH.

### Pitfall 9: AI Hallucination or Policy Error Makes a Business Commitment

**What goes wrong:** The agent invents a product, price, refund, substitution, delivery promise, or medical recommendation, or autonomously acts when the customer intended something else.

**Why it happens:** Language models can generate unsupported facts. The current prompt explicitly tells the model to pick the closest product when ambiguous and add it without asking. It lacks complete handoff rules for medical reactions, complaints, images, voice notes, payment questions, and order changes after `to_do`.

**Consequences:** Customer harm, incorrect orders, damaged trust, financial loss, and unsafe skincare advice.

**Warning signs:**
- Evaluation failures cluster around ambiguity, Arabic variants, noisy text, or medical terms.
- The model uses a tool when the expected action is handoff or clarification.
- Replies contain prices or policy claims not present in authoritative data.
- The aunt must frequently correct orders or promises after the fact.
- No automation-pause flag exists during human handoff.

**Prevention:**
- Put deterministic policy gates before the model: risky categories always hand off; only `to_do` orders may be automatically changed; refunds, discounts, substitutions, price changes, and medical advice are never autonomous.
- Require explicit product identity and quantity validation before a mutating tool executes.
- Ground factual responses in current catalog/policy data and permit "I do not know."
- Implement durable handoff state that pauses automation until the aunt resolves it.
- Define release thresholds by risk class, not only aggregate intent accuracy.

**Verification evidence:**
- Representative Arabic, English, noisy, adversarial, and multi-turn evaluation suite with recorded model version and prompt version.
- Zero autonomous action in prohibited categories across the release set.
- Tool-call precision and false-action rate meet explicit thresholds.
- Red-team tests for price changes, refunds, medical reactions, angry complaints, and ambiguous product names.
- Pilot audit compares AI decision, tool action, aunt correction, and final outcome.

**Contingency/rollback:**
- Switch to deterministic menu/order commands plus human handoff.
- Disable individual mutating tools through configuration.
- Roll back prompt/model version and replay failed cases before re-enabling.

**Milestone mapping:** M3 blocker; M5 validates thresholds with real pilot conversations.  
**Confidence:** HIGH.

### Pitfall 10: Tool Errors and Prompt Injection Cross the Trust Boundary

**What goes wrong:** A customer message or dashboard-authored product description manipulates the model into ignoring policy, a malformed tool input causes an exception, or tool errors leak internal details back to the customer.

**Why it happens:** Catalog and knowledge content are concatenated into the system prompt. Product descriptions are operator-editable. Tool schemas are not marked strict, runtime checks are incomplete, quantity is unbounded, and exceptions are converted into tool result text or customer-visible AI error text.

**Consequences:** Unauthorized cart actions, denial of service, leaked internals, inflated orders, and policy bypass.

**Warning signs:**
- Inputs such as "ignore previous instructions" change tool selection.
- Product descriptions contain instruction-like text or markup.
- Tool exceptions appear in WhatsApp replies.
- Very large quantities, malformed numeric values, or long addresses reach database functions.
- The model's natural-language reply is treated as proof that a tool succeeded.

**Prevention:**
- Treat customer, catalog, knowledge, OCR, and tool-result text as untrusted data.
- Keep policy in trusted code and system instructions; pass untrusted records in clearly delimited structured data rather than allowing them to become instructions.
- Use strict tool schemas where supported and enforce server-side allowlists, ranges, state checks, authorization, and idempotency regardless of model output.
- Return stable error codes to the model and generic messages to the customer.
- Add input size, quantity, and rate limits before AI invocation.

**Verification evidence:**
- Prompt-injection suite covers direct attacks and malicious catalog/knowledge content.
- Property and boundary tests for every tool argument.
- Logs correlate model tool request, validated arguments, execution result, and business state change without storing unnecessary content.
- No stack trace, SQL text, secret, or provider error is present in customer replies.

**Contingency/rollback:**
- Disable AI tool use while preserving deterministic commands.
- Quarantine the offending catalog/knowledge record.
- Rotate credentials if logs or responses exposed secrets.

**Milestone mapping:** M3 owns AI/tool isolation; M4 validates safe operator-authored content; M5 red-teams the deployed system.  
**Confidence:** HIGH.

### Pitfall 11: AI Latency, Rate Limits, or Cost Exhaustion Breaks the Webhook

**What goes wrong:** Two-call tool flows exceed webhook latency, Anthropic returns 429/500/504/529, or unexpected usage consumes the monthly budget and disables service.

**Why it happens:** AI runs inline in the webhook. The application creates a new client per request, does not record token usage/request IDs, does not set an application-specific timeout, and returns provider exception text to customers. Full catalog and selected knowledge increase input tokens.

**Consequences:** Slow replies, duplicate webhook delivery, missing replies, uncontrolled spend, and difficult provider incident diagnosis.

**Warning signs:**
- Rising p95/p99 AI latency or webhook duration.
- 429, 504, or 529 errors without `retry-after` handling.
- Token use or cost per successful order is unknown.
- Sudden traffic or repeated abusive messages cause a spend spike.
- The service has no deterministic response when Claude is unavailable.

**Prevention:**
- Decouple webhook acknowledgement from AI processing.
- Set bounded connect/read/overall timeouts and limited jittered retries only where safe.
- Capture Anthropic request ID, model, stop reason, input/output/cache tokens, latency, and outcome.
- Set customer-controlled workspace/monthly spend limits and application daily budgets.
- Rate-limit per phone and globally; cache stable prompt/catalog content where appropriate.
- Provide deterministic menu, cart, status, and handoff fallbacks.

**Verification evidence:**
- Fault tests for timeout, 429 with retry-after, 500, 504, 529, malformed tool output, and budget exhaustion.
- Dashboard or report for AI cost per conversation/order and daily spend.
- Release threshold for p95 response time and maximum calls per inbound message.
- Provider outage drill proves orders can be manually handled.

**Contingency/rollback:**
- Disable conversational AI and keep hard commands plus human handoff.
- Lower per-phone rate limits and stop nonessential broadcast improvement.
- Switch model only after the evaluation suite passes, not during an incident without validation.

**Milestone mapping:** M3 owns budgets and fallbacks; M2 ensures AI cannot block webhook acceptance; M5 validates alerts.  
**Confidence:** HIGH.

### Pitfall 12: Dashboard Authentication and CSRF Allow Unauthorized Business Actions

**What goes wrong:** Anyone who guesses the shared password or obtains the static cookie can update products, change order status, delete catalog data, or broadcast to all customers. A malicious site can trigger authenticated POST requests from the aunt's browser.

**Why it happens:** The session value is a deterministic hash of the secret and password, has no expiry or server-side revocation, and is accepted by all dashboard APIs. The cookie is not `Secure`; logout is a state-changing GET; login is not throttled; and there is no CSRF token or origin check. `SameSite=Lax` is defense in depth, not a complete CSRF control.

**Consequences:** Customer spam, order corruption, data loss, account lockout, and privacy breach.

**Warning signs:**
- The cookie remains valid after password change or logout from another device.
- Repeated login attempts are unlimited and unalerted.
- Cross-origin POST proof-of-concept changes data.
- There is no audit record of who changed an order or product.
- The default password or secret starts successfully in production.

**Prevention:**
- Use a standard server-side session or established authentication provider, even if there is only one operator.
- Store a strong password hash, issue random sessions, rotate on login, and enforce idle and absolute expiry.
- Set `Secure`, `HttpOnly`, and appropriate `SameSite`; serve authenticated pages only over TLS.
- Add CSRF tokens or a robust double-submit pattern plus Origin/Referer verification for state-changing requests.
- Rate-limit login and alert on repeated failures.
- Require POST with CSRF protection for logout and all mutations.
- Add authorization and audit logging at the API boundary.

**Verification evidence:**
- Security tests for brute force, session expiry, logout revocation, cookie flags, CSRF, origin mismatch, and direct API access.
- Browser inspection of production cookies over HTTPS.
- Audit log shows actor, action, target, before/after summary, and time.
- No production startup with known default credentials.

**Contingency/rollback:**
- Revoke all sessions, rotate secret/password, and temporarily restrict dashboard access.
- Disable broadcast and destructive product actions independently.
- Restore affected data or reverse actions using the audit trail.

**Milestone mapping:** M4 blocker; M5 runs a focused security acceptance test.  
**Confidence:** HIGH.

## Moderate Pitfalls

### Pitfall 13: Background Jobs Run Zero Times or More Than Once

**What goes wrong:** Follow-ups, monthly reports, and retries are missed during restarts or execute once per web worker. Multiple retry processors act on the same row.

**Why it happens:** APScheduler is created inside the web process with an in-memory schedule. Every process runs startup hooks. The retry query selects eligible rows without row locking, leasing, or a claimed state. The required `monthly_snapshots` table is absent.

**Consequences:** Duplicate customer messages, missed follow-ups, repeated invoices, and silent retry backlog.

**Warning signs:**
- Two identical job logs at the same timestamp.
- Scaling web replicas changes job volume.
- Old due rows remain in `retry_queue`.
- Rows reach `max_attempts` without an alert.
- Monthly report fails on a fresh database.

**Prevention:**
- Run one dedicated scheduler/worker process for the pilot, separate from web replicas.
- Persist job state or use database-backed due-work tables.
- Claim work atomically with a lease or `FOR UPDATE SKIP LOCKED`.
- Add unique business keys to prevent duplicate follow-up/invoice actions.
- Define misfire, coalescing, timeout, and dead-letter behavior.
- Add the missing schema through migrations and test every scheduled job.

**Verification evidence:**
- Multi-process test proves each due business action executes once.
- Restart test proves due work resumes.
- Dead-letter alert fires when retries are exhausted.
- Job dashboard shows last start, last success, duration, next run, and backlog.

**Contingency/rollback:**
- Stop the worker without stopping inbound order capture.
- Let the aunt process a visible due-work list manually.
- Requeue only after checking whether the external side effect already occurred.

**Milestone mapping:** M2 owns worker topology and retry semantics; M1 owns job tables; M5 validates operations.  
**Confidence:** HIGH.

### Pitfall 14: Privacy and Retention Exist Only as Documentation

**What goes wrong:** Phone numbers, addresses, conversations, handoff records, medical-reaction messages, retry errors, and logs accumulate indefinitely or are copied into evaluation data without anonymization.

**Why it happens:** `chat_history` and `retry_queue` have no cleanup job. Full message text, name, and phone are logged. The 12-month conversation/handoff policy is not implemented, and order/invoice retention is not separately defined.

**Consequences:** Excessive breach impact, policy noncompliance, inability to honor deletion/anonymization decisions, and unsafe reuse of sensitive conversations.

**Warning signs:**
- No data inventory classifies each table/log field, purpose, access, and retention.
- Old chat and retry rows continue growing.
- Logs contain full phone numbers, addresses, message bodies, or provider exception text.
- Evaluation files contain directly identifiable customer text.
- Broadcast opt-out exists in test labels but not in production state.

**Prevention:**
- Implement a field-level data inventory and minimize collection.
- Enforce 12-month conversation/handoff anonymization with a tested scheduled job.
- Define separate legal/accounting retention for orders and invoices before launch.
- Redact structured logs and restrict access to production data.
- Anonymize evaluation exports before they leave production.
- Add consent and opt-out state for marketing communication.
- Document how backup retention limits deletion guarantees.

**Verification evidence:**
- Retention tests with aged fixtures prove deletion/anonymization and preserve required order records.
- Sample production logs pass a PII review.
- Access review shows only required operators/services can view personal data.
- Opt-out request immediately suppresses future marketing sends.
- Data inventory and retention schedule are owner-approved.

**Contingency/rollback:**
- Suspend exports, broadcasts, and nonessential conversation logging.
- Purge or anonymize affected active records using a reviewed script and preserve an audit record.
- Rotate credentials and follow the incident runbook if exposure occurred.

**Milestone mapping:** M1 owns database retention; M2 owns log redaction; M3 owns AI/evaluation data; M4 owns consent controls; M5 verifies the complete policy.  
**Confidence:** HIGH for implementation gaps; legal retention duration requires local professional confirmation.

### Pitfall 15: Monitoring Reports Uptime While Business Work Is Failing

**What goes wrong:** Railway shows a running deployment, but Meta sends fail, the webhook returns false 200s, Claude is unavailable, Supabase rejects writes, or scheduled work is stuck.

**Why it happens:** There is only standard logging and no external error tracking, business metrics, alerts, or synthetic checks. A deployment health check is not sufficient ongoing business monitoring.

**Consequences:** The aunt discovers incidents from customer complaints, and recovery starts after orders are already lost.

**Warning signs:**
- No alert owner or tested notification channel.
- No metric for inbound accepted/processed/failed, outbound accepted/delivered/failed, duplicate events, order creation, AI errors, or job backlog.
- Logs cannot correlate a Meta event, customer-safe identifier, order, AI request, and outbound message.
- A "successful" send count ignores HTTP response status.

**Prevention:**
- Use structured logs with correlation IDs and redacted identifiers.
- Check and classify every external HTTP response.
- Add metrics and alerts for webhook acceptance/processing, queue age, duplicate rate, order failures, outbound delivery, AI errors/cost, database errors, job heartbeat, and login abuse.
- Add external uptime/readiness checks and a small synthetic production-safe workflow.
- Write alerts for the aunt in plain operational language with one action and one escalation path.

**Verification evidence:**
- Alert drills for app down, database down, Meta rejection, Claude outage, dead job worker, and retry exhaustion.
- Synthetic check history and dashboard screenshots.
- Runbook links included in alerts.
- Measured detection time meets the launch target.

**Contingency/rollback:**
- Switch to manual operations and disable the failing subsystem.
- Use provider status pages and captured request IDs for escalation.
- Reconcile inbound and outbound events after service recovery.

**Milestone mapping:** Instrumentation begins in M1-M4; M5 blocks launch until alerts are exercised.  
**Confidence:** HIGH.

### Pitfall 16: The Pilot Tests Features but Not Operations

**What goes wrong:** Selected customers can place orders, but nobody tests duplicate events, failed sends, handoffs, status corrections, downtime, reconciliation, or the aunt operating alone.

**Why it happens:** Teams treat pilot success as "happy path worked" instead of proving the entire business lifecycle and recovery behavior.

**Consequences:** The public launch exposes untested exception paths and depends on the student owner being continuously available.

**Warning signs:**
- Pilot has no cohort limit, duration, success metrics, stop criteria, or daily review.
- Test orders are deleted instead of reconciled.
- No handoff, cancellation, delivery, invoice, retry, or outage scenario is exercised.
- The aunt cannot explain open work or recover without developer help.

**Prevention:**
- Run internal dogfood first, then a named small customer cohort, then a limited-volume pilot.
- Define pilot metrics: order correctness, duplicate rate, message failure rate, handoff response time, aunt correction rate, AI cost/order, and unresolved incidents.
- Reconcile WhatsApp conversations, inbound events, orders, lines, outbox, and dashboard every day.
- Use explicit stop conditions for data loss, duplicate order, unauthorized access, unsafe AI response, or unavailable manual fallback.
- Freeze noncritical features during the pilot.

**Verification evidence:**
- Signed pilot checklist and daily reconciliation record.
- All required lifecycle and failure scenarios completed.
- Defect list has no unresolved critical/high launch blocker.
- Aunt completes an observed shift without developer intervention.

**Contingency/rollback:**
- Pause new pilot participants immediately.
- Keep existing orders visible and finish them manually.
- Roll back automation by feature flag while retaining event/audit data for diagnosis.

**Milestone mapping:** M5 owns the pilot, but M1-M4 must provide the evidence and controls it exercises.  
**Confidence:** HIGH.

### Pitfall 17: Operator Training and Incident Response Depend on the Developer

**What goes wrong:** The aunt cannot tell whether an order needs action, a customer is waiting for handoff, a message failed, or the system should be paused. The student owner becomes the only person who can recover access or diagnose an incident.

**Why it happens:** Technical runbooks mirror code rather than operator decisions, access recovery is informal, and incident drills are postponed until after launch.

**Consequences:** Long incidents, contradictory customer replies, unsafe workarounds, and abandoned automation.

**Warning signs:**
- Alerts expose stack traces rather than a clear operator action.
- No visible inbox for unresolved handoffs and failed notifications.
- Meta, Supabase, Railway, domain, and Anthropic accounts have one owner.
- Recovery codes, billing access, and support contacts are unavailable to a trusted backup.
- The aunt needs direct database or Railway access for normal work.

**Prevention:**
- Design the dashboard around queues: new orders, handoffs, failed sends, retries exhausted, and items needing reconciliation.
- Create one-page Arabic-first runbooks for common incidents and escalation.
- Train with realistic scenarios, not a feature tour.
- Establish primary/backup account owners, MFA, password-manager storage, and access review.
- Define incident severity, incident commander, customer communication, evidence capture, and post-incident review.

**Verification evidence:**
- Aunt passes a task-based acceptance session and incident drill.
- Backup owner proves account recovery without using the primary owner's device.
- Runbooks are linked from UI/alerts and have a review date.
- Incident log template is used during at least one drill.

**Contingency/rollback:**
- Pause automation and continue via manual WhatsApp.
- Use a prewritten customer delay message.
- Escalate to the owner only after the aunt follows the first-response checklist.

**Milestone mapping:** M4 owns operator-facing controls; M5 owns training, access recovery, and incident drills.  
**Confidence:** HIGH.

### Pitfall 18: One-Month Schedule Pressure Removes the Safety Gates

**What goes wrong:** The team spends the month polishing AI/UI behavior while Meta registration, database recovery, idempotency, and operations remain unfinished, then launches because the date arrived.

**Why it happens:** External approvals are unpredictable, existing features create false confidence, and production evidence takes longer than implementation.

**Consequences:** Public launch with known critical defects, no rollback, and no time for a meaningful pilot.

**Warning signs:**
- M1 or M2 is still open halfway through the month.
- Meta registration has no daily escalation.
- Optional features enter scope after the first week.
- Tests are counted as complete without production-like evidence.
- Pilot duration is repeatedly shortened.

**Prevention:**
- Freeze scope to launch blockers: Meta transport, database safety, durable processing, AI/handoff safety, dashboard security, observability, and operator readiness.
- Establish dated go/no-go gates and a final change freeze.
- Track external dependencies separately from code tasks.
- Prefer disabling risky features over partially hardening them.
- Reserve the final week for integrated testing, pilot, drills, training, and defect closure.

**Verification evidence:**
- Weekly gate review records milestone evidence and unresolved risks.
- Critical path has named owners and dates.
- Deferred scope list is explicit and approved.
- Go-live decision references objective exit criteria, not percentage complete.

**Contingency/rollback:**
- Delay public cutover while preserving the controlled pilot or manual operation.
- Ship a reduced mode with AI tools, broadcasts, or schedules disabled if that mode independently passes its acceptance criteria.
- Never substitute the Meta test number for a real-number production handoff.

**Milestone mapping:** Cross-cutting; M5 enforces the final go/no-go decision.  
**Confidence:** HIGH.

## Minor Pitfalls

### Pitfall 19: Version Drift and Stale Assumptions Cause Avoidable Outages

**What goes wrong:** A broad dependency update, stale Meta Graph API version, deprecated FastAPI lifecycle, or obsolete platform instruction breaks a deployment.

**Warning signs:** No lock file, no dependency update test, hard-coded API version, or documentation without a review date.

**Prevention:** Lock production dependencies, make provider API versions configurable, test upgrades in staging, and date every operational runbook.

**Verification evidence:** Reproducible clean build, dependency inventory, live provider smoke test, and scheduled review task.

**Contingency/rollback:** Restore the previous lock/image, keep schema backward compatible, and disable only the affected integration.

**Milestone mapping:** M2 prevents runtime drift; M5 verifies deployed versions.  
**Confidence:** HIGH.

### Pitfall 20: Business-State Terminology Is Inconsistent

**What goes wrong:** Code, dashboard, aunt, and customer interpret `ready`, `delivered`, and `done` differently, causing incorrect notifications and automatic order-change decisions.

**Warning signs:** Status changes can skip states, pickup and delivery share unclear wording, and tests assert labels without validating allowed transitions.

**Prevention:** Define one state machine with role-specific labels, allowed transitions, reversals, and the exact point after which automation must hand off.

**Verification evidence:** Transition tests and aunt-approved Arabic/English wording.

**Contingency/rollback:** Freeze automatic status messages and let the aunt correct the order through an audited action.

**Milestone mapping:** M1 owns constraints, M3 owns automation rules, M4 owns UI, M5 validates real workflows.  
**Confidence:** HIGH.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Required Mitigation / Exit Evidence |
|-------------|----------------|-------------------------------------|
| **M1 - Schema baseline** | Remote/manual schema differs from Git | Clean rebuild from migrations; migration history matches remote |
| **M1 - Database access** | Generic SQL RPC has excessive privilege | Reviewed function definitions, grants, role/key matrix, RLS tests |
| **M1 - Order integrity** | Partial or duplicate orders | Transactional order creation, unique idempotency key, fault tests |
| **M1 - Recovery** | Backup cannot meet business RPO/RTO | Timed restore drill and reconciliation checklist |
| **M1 - Retention** | Personal data grows forever | Implemented and tested anonymization/cleanup jobs |
| **M2 - Meta onboarding** | Number/token/subscription not production-ready | Real-number inbound and outbound evidence before M2 closes |
| **M2 - Webhook** | 422, forgery, timeout, false 200 | Envelope contract tests, HMAC tests, durable inbox, fast acknowledgement |
| **M2 - Deployment** | Unsafe defaults or debug routes | Fail-closed startup tests, route inventory, lock file |
| **M2 - Background work** | Duplicate scheduler/retry execution | Dedicated worker and atomic claim/lease test |
| **M2 - Rollback** | Image rollback conflicts with schema | Expand-contract migration and Railway rollback drill |
| **M3 - Agent policy** | Unsafe autonomous commitment | Deterministic policy gate and zero prohibited actions in evals |
| **M3 - Tool use** | Ambiguous or injected tool call | Strict schemas, server validation, injection tests |
| **M3 - Availability/cost** | Provider failure blocks replies or overspends | Timeouts, budgets, usage telemetry, deterministic fallback |
| **M3 - Handoff** | Bot continues after escalation | Durable pause state, aunt alert, visible inbox, resolution audit |
| **M4 - Authentication** | Permanent shared bearer session | Expiring revocable session, cookie flags, brute-force protection |
| **M4 - CSRF/authorization** | Cross-site or direct API mutation | CSRF/origin tests and server-side authorization |
| **M4 - Broadcast** | Policy or consent violation | Approved templates, opt-out enforcement, send-result accuracy |
| **M4 - Operator UX** | Failures hidden from aunt | Action queues, plain-language errors, audited recovery actions |
| **M5 - Pilot** | Happy path only | Controlled cohort, failure scenarios, daily reconciliation, stop criteria |
| **M5 - Monitoring** | Incident detected by customers | Exercised alerts for service, DB, Meta, AI, worker, and auth failures |
| **M5 - Handoff** | Owner remains single point of failure | Aunt task test, backup access recovery, runbooks, incident drill |
| **M5 - Cutover** | Deadline overrides evidence | Signed go/no-go with no unresolved critical/high launch blockers |

## Recommended Go/No-Go Rules

Public cutover is **NO-GO** if any of the following remains true:

- The real Meta number cannot complete inbound, outbound, template, and delivery-status tests.
- Webhook signature verification, durable acceptance, and idempotent replay are not proven.
- Duplicate or partial order creation remains possible under replay/fault tests.
- Generic Supabase RPC privilege is not understood and restricted.
- A backup restore has not been tested.
- AI can autonomously act in prohibited or uncertain scenarios.
- Human handoff does not pause automation and create visible operator work.
- Dashboard authentication or CSRF tests fail.
- Outbound non-2xx responses can still be counted as successful.
- Scheduled work can duplicate across processes or fail without alert.
- The aunt cannot complete daily work and first-response incident actions alone.
- The pilot has an unresolved critical/high defect or has not met its minimum duration and scenario coverage.

## Sources

### Meta / WhatsApp

- Meta official WhatsApp Cloud API Postman documentation: https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api  
  **Confidence:** HIGH. Used for required assets, WABA subscription, token behavior, phone registration, two-step PIN, and Embedded Signup registration window.
- WhatsApp Business Messaging Policy: https://www.whatsappbusiness.com/policy/  
  **Confidence:** HIGH. Used for messaging-policy and consent/opt-out risk framing.
- WhatsApp Business Platform: https://www.whatsappbusiness.com/products/business-platform/  
  **Confidence:** HIGH.

### Supabase

- Production checklist: https://supabase.com/docs/guides/deployment/going-into-prod  
  **Confidence:** HIGH. RLS, MFA, backups, availability, and deployment controls.
- Row Level Security: https://supabase.com/docs/guides/database/postgres/row-level-security  
  **Confidence:** HIGH.
- Database migrations: https://supabase.com/docs/guides/deployment/database-migrations  
  **Confidence:** HIGH. Direct remote edits bypass migration history; migrations should be tested and pushed consistently.
- Database backups: https://supabase.com/docs/guides/platform/backups  
  **Confidence:** HIGH.
- Supabase CLI reference via Context7 `/supabase/cli`: `db reset`, `db diff`, and `db push`.  
  **Confidence:** HIGH.

### FastAPI, Railway, and Background Jobs

- FastAPI deployment concepts: https://fastapi.tiangolo.com/deployment/concepts/  
  **Confidence:** HIGH. Startup, restart, workers, and single-run pre-start tasks.
- FastAPI lifespan events: https://fastapi.tiangolo.com/advanced/events/  
  **Confidence:** HIGH. Lifespan is the recommended startup/shutdown mechanism.
- Railway health checks: https://docs.railway.com/deployments/healthchecks  
  **Confidence:** HIGH.
- Railway deployment rollback: https://docs.railway.com/deployments/deployment-actions  
  **Confidence:** HIGH. Rollback restores the prior successful image and custom variables within retention limits.
- APScheduler official documentation via Context7 `/agronholm/apscheduler`.  
  **Confidence:** HIGH for the multi-scheduler coordination and persistent-store principles; implementation must account for this project using APScheduler 3.x.

### Anthropic / AI Safety

- Tool definitions and strict tool use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools  
  **Confidence:** HIGH.
- Prompt injection mitigations: https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks  
  **Confidence:** HIGH.
- Hallucination reduction: https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations  
  **Confidence:** HIGH.
- Evaluation design: https://platform.claude.com/docs/en/test-and-evaluate/develop-tests  
  **Confidence:** HIGH.
- API errors: https://platform.claude.com/docs/en/api/errors  
  **Confidence:** HIGH. Includes 429, 500, 504, and 529 behavior.
- Rate and spend limits: https://platform.claude.com/docs/en/api/rate-limits  
  **Confidence:** HIGH.
- Anthropic Python SDK via Context7 `/anthropics/anthropic-sdk-python`.  
  **Confidence:** HIGH. Used for SDK retry behavior and error handling.

### Web Security and Operations

- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html  
  **Confidence:** HIGH.
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html  
  **Confidence:** HIGH.
- OWASP CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html  
  **Confidence:** HIGH. `SameSite` is defense in depth and does not replace proper CSRF controls in most deployments.
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html  
  **Confidence:** HIGH.
- OWASP Input Validation Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html  
  **Confidence:** HIGH.

## Research Gaps Requiring Phase-Specific Validation

- Meta's exact reason for the current real-number registration failure is account-specific and cannot be resolved from repository research. M2 needs the live account state and support case.
- Template approval timing and final category decisions are controlled by Meta and should not be assumed.
- The exact definitions and grants for production `run_query` and `run_exec` are not in the repository. M1 must inspect the live project.
- Backup features and retention depend on the selected Supabase plan. M1 must record the actual plan and restore options.
- Legal/accounting retention for Palestinian business records and any applicable customer privacy duties require local professional confirmation. The technical design should support the agreed policy without storing unnecessary medical or payment data.
