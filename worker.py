import asyncio
import json
import logging
import signal
import sys
from typing import NoReturn

from app.services import worker_utils, worker_tasks
from app.db import database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("worker")

# Flag for graceful shutdown
shutdown_requested = False

def handle_exit(sig, frame):
    global shutdown_requested
    log.info("Shutdown requested via signal...")
    shutdown_requested = True

async def inbox_loop() -> None:
    """Process incoming webhook events from the 'webhook_events' table."""
    log.info("Starting inbox loop...")
    while not shutdown_requested:
        try:
            event = worker_utils.claim_inbox_event()
            if event:
                event_id = event["id"]
                log.info("Processing inbox event %s (wamid: %s)", event_id, event.get("wamid"))
                
                try:
                    worker_tasks.handle_inbox_event(event)
                    worker_utils.update_job_status("webhook_events", event_id, "processed")
                    log.info("Successfully processed inbox event %s", event_id)
                except Exception as e:
                    log.error("Failed to process inbox event %s: %s", event_id, e)
                    worker_utils.update_job_status("webhook_events", event_id, "failed")
                
                continue # Check for more jobs immediately
            
            await asyncio.sleep(1)
        except Exception as e:
            log.error("Error in inbox_loop: %s", e)
            await asyncio.sleep(5)

async def outbox_loop() -> None:
    """Process outgoing jobs from the 'outbox_jobs' table."""
    log.info("Starting outbox loop...")
    while not shutdown_requested:
        try:
            job = worker_utils.claim_outbox_job()
            if job:
                job_id = job["id"]
                log.info("Processing outbox job %s (transport: %s)", job_id, job.get("transport"))
                
                # TODO: Implement actual sending logic (Phase 08 Wave 3+)
                # For now, we just mark it as sent.
                
                worker_utils.update_job_status("outbox_jobs", job_id, "sent")
                log.info("Successfully processed outbox job %s", job_id)
                continue # Check for more jobs immediately
            
            await asyncio.sleep(1)
        except Exception as e:
            log.error("Error in outbox_loop: %s", e)
            await asyncio.sleep(5)

async def main() -> None:
    """Main entry point for the worker process."""
    if "--dry-run" in sys.argv:
        log.info("Dry run requested. Validating environment and exiting.")
        database.validate_schema()
        log.info("Dry run successful.")
        return

    if "--test-inbox" in sys.argv:
        log.info("Test-inbox requested. Simulating an inbox event...")
        database.validate_schema()
        mock_wamid = f"test-{hash(str(asyncio.get_event_loop().time()))}"
        mock_payload = {"from_number": "972591234567", "text": "hello test", "wa_name": "Tester"}
        database.execute(
            "INSERT INTO webhook_events (wamid, payload, status) VALUES (%s, %s, 'pending')",
            (mock_wamid, json.dumps(mock_payload))
        )
        # Run one iteration of inbox_loop logic manually
        event = worker_utils.claim_inbox_event()
        if event:
            try:
                worker_tasks.handle_inbox_event(event)
                worker_utils.update_job_status("webhook_events", event["id"], "processed")
                log.info("Test-inbox: Successfully processed mock event.")
            except Exception as e:
                log.error("Test-inbox: Failed to process mock event: %s", e)
                worker_utils.update_job_status("webhook_events", event["id"], "failed")
        else:
            log.error("Test-inbox: Failed to claim the mock event.")
        return

    log.info("AuntOps Worker starting...")
    
    # Register signal handlers for graceful shutdown
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, handle_exit)
    else:
        # On Windows, signal.signal doesn't work as well for SIGINT in some envs,
        # but let's try.
        signal.signal(signal.SIGINT, handle_exit)

    # Initialize database connection and validate schema
    try:
        database.validate_schema()
        log.info("Database schema validated.")
    except Exception as e:
        log.critical("Worker failed to start due to schema validation error: %s", e)
        sys.exit(1)

    # Run inbox and outbox loops concurrently
    await asyncio.gather(
        inbox_loop(),
        outbox_loop()
    )
    
    log.info("Worker stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
