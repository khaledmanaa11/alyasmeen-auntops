# Phase 08 Plan 03: Outbox Standardisation Summary

Standardized outbound communications using the Transactional Outbox Pattern and moved PDF generation to the background worker.

## Key Changes

### 1. Unified Outbox Helper (`app/services/outbox.py`)
- Implemented `enqueue_outbox(recipient, payload, transport)` to decouple business logic from delivery.
- All outbound messages (WhatsApp) and background tasks (PDF generation) now flow through the `outbox_jobs` table.

### 2. Outbox Execution Engine (`worker.py`)
- Implemented `execute_outbox_job(job)` in the worker process.
- Supports `whatsapp_meta` (text, buttons, documents) and `pdf_generation`.
- `pdf_generation` logic:
    - Fetches order and line items.
    - Generates Hebrew PDF using `pdf_invoice` service.
    - Delivers resulting PDF to the customer via WhatsApp in the same background task.

### 3. Refactored `worker_tasks.py`
- Removed direct dependencies on `whatsapp_meta` and `whatsapp_dev`.
- All `send_text` and `send_buttons` calls now transparently queue jobs in the outbox.
- Added a trigger to queue `pdf_generation` immediately after an order is confirmed.

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

### Automated Tests
- `python worker.py --test-outbox`: Verified execution of queued text messages.
- `python worker.py --test-inbox`: Verified that incoming messages correctly queue replies in the outbox.
- `pytest tests/integration/test_transport.py`: All 5 ingestion tests passed.

### Manual Verification
- Queued a `pdf_generation` job for `order_id=5`.
- Verified worker log shows PDF generation (font subsetting, layout) and successful delivery via mock transport.
- Verified `outbox_jobs` status updates from `pending` to `sent`.

## Known Stubs

None.

## Self-Check: PASSED
- [x] All tasks executed.
- [x] Each task committed individually.
- [x] Outbox helper implemented.
- [x] Message senders refactored.
- [x] PDF generation moved to worker.
- [x] SUMMARY.md created.
