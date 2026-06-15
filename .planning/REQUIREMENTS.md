# Requirements: ALYASMEEN AuntOps M2

## Milestone Archive
- [v1.0 (M1 Requirements)](.planning/milestones/v1.0-REQUIREMENTS.md)

## M2 Requirements: FastAPI → Production

### 1. Web+Worker Architecture (REQ-M2-01)
- **Two-Process Split**: Separate `web` (FastAPI) and `worker` (Processor) services.
- **Durable Inbox**: Persist every Meta webhook event to `webhook_events` before acknowledging 200 OK.
- **Durable Outbox**: Persist every outbound intent (WhatsApp, PDF, Email) to `outbox_jobs` within the business transaction.
- **Worker Process**: Dedicated process to claim and execute `webhook_events` and `outbox_jobs` with backoff retries.
- **Single Scheduler**: Run APScheduler only in the worker process to avoid duplicate jobs.

### 2. Meta Transport Hardening (REQ-M2-02)
- **Signature Verification**: Validate `X-Hub-Signature-256` using `WA_META_APP_SECRET`.
- **Envelope Parsing**: Correctly handle Meta's nested JSON structure (batches, statuses, interactive replies).
- **Idempotency**: Use Meta's `wamid` to prevent duplicate processing of the same message.
- **Error Semantics**: Return 5xx if database persistence fails (allowing Meta retry); return 200 for successful ingest or confirmed duplicates.

### 3. Messaging Reliability (REQ-M2-03)
- **Template Support**: Implement `send_template` in `whatsapp_meta.py` for business-initiated messages.
- **Follow-up Migration**: Update `followup.py` to use an approved Meta template (REQ-M2-03-A).
- **Report Migration**: Update `monthly_report.py` to use an approved Meta template for the Aunt (REQ-M2-03-B).
- **Outbox Integration**: All outbound messages must be queued in the outbox, not sent inline with requests.

### 4. Operations & Observability (REQ-M2-04)
- **Structured Logging**: Use `structlog` to emit JSON logs with correlation IDs (`request_id`, `wamid`, `order_id`).
- **Health Checks**: Implement `/livez` (process) and `/readyz` (dependency check) endpoints.
- **Lifespan Migration**: Move startup/shutdown logic to FastAPI `lifespan` handler.
- **Railway Hardening**: Configure single-instance migrations via pre-deploy and health-check-aware rollouts.

### 5. Meta Onboarding Tracking (REQ-M2-05)
- **Onboarding Doc**: Create `docs/META_ONBOARDING.md` to track asset IDs and approval states.
- **Asset Verification**: Verify Phone ID, WABA ID, and System User Token permissions.
- **Template Approval**: Track the submission and approval status of required templates (Arabic/English).

## Non-Functional Requirements
- **Latency**: Webhook acknowledgment < 2 seconds.
- **Reliability**: No message lost due to process restart or AI service outage.
- **Security**: Fail closed if `WA_META_APP_SECRET` is missing in production.
