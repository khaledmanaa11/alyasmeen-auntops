import asyncio
import json
import logging
import signal
import sys
from typing import NoReturn

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services import worker_utils, worker_tasks, whatsapp_meta, pdf_invoice
from app.services.config import Config
from app.db import database
from app.routers.whatsapp_helpers import get_customer_name, get_latest_order

# Job imports for scheduler
from app.services.backup import run_backup
from app.services.followup import send_followups
from app.services.monthly_report import send_monthly_report
from app.services.retention import run_retention
from app.services.retry_queue import process_retries

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("worker")

# Flag for graceful shutdown
shutdown_requested = False
_scheduler = AsyncIOScheduler()

def register_scheduled_jobs():
    """Register all background jobs with the scheduler."""
    _scheduler.add_job(send_followups, "interval", hours=6, id="followup")
    _scheduler.add_job(send_monthly_report, "cron", day=1, hour=8, minute=0, id="monthly_report")
    _scheduler.add_job(process_retries, "interval", minutes=15, id="retry_queue")
    _scheduler.add_job(run_backup, "cron", hour=3, minute=0, id="nightly_backup")
    _scheduler.add_job(run_retention, "cron", hour=4, minute=0, id="daily_retention")

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

async def execute_outbox_job(job: dict) -> None:
    """Execute a single outbox job based on its transport and payload."""
    transport = job.get("transport")
    recipient = job.get("recipient")
    payload = job.get("payload") or {}
    
    if transport == "whatsapp_meta":
        msg_type = payload.get("type", "text")
        if msg_type == "text":
            whatsapp_meta.send_text(recipient, payload.get("body", ""))
        elif msg_type == "buttons":
            whatsapp_meta.send_buttons(recipient, payload.get("body", ""), payload.get("buttons", []))
        elif msg_type == "document":
            if "url" in payload:
                whatsapp_meta.send_document(
                    recipient, 
                    payload["url"], 
                    payload.get("filename", "document.pdf"), 
                    payload.get("caption")
                )
            else:
                log.warning("whatsapp_meta document job %s missing URL", job.get("id"))
    
    elif transport == "pdf_generation":
        order_id = payload.get("order_id")
        if not order_id:
            raise ValueError("pdf_generation job missing order_id in payload")
            
        log.info("Generating PDF for order %s (recipient: %s)", order_id, recipient)
        
        # 1. Fetch order details
        order_rows = database.query("SELECT * FROM orders WHERE id = %s", (order_id,))
        if not order_rows:
            raise ValueError(f"Order {order_id} not found for PDF generation")
        order = order_rows[0]
        
        # 2. Fetch order lines
        lines = database.query("SELECT * FROM order_lines WHERE order_id = %s", (order_id,))
        
        # 3. Generate PDF
        customer_name = get_customer_name(recipient) or recipient
        pdf_bytes = pdf_invoice.generate_invoice_pdf(
            order_id=order_id,
            customer_name=customer_name,
            order_date=str(order["created_at"])[:10],
            lines=lines,
            total=float(order["total"])
        )
        
        # 4. Send PDF via WhatsApp
        whatsapp_meta.send_document_bytes(
            to=recipient,
            pdf_bytes=pdf_bytes,
            filename=f"invoice-ORD-{order_id:04d}.pdf",
            caption="إليك فاتورة طلبك من الياسمين ✨"
        )
    else:
        log.warning("Unknown transport type: %s", transport)

async def outbox_loop() -> None:
    """Process outgoing jobs from the 'outbox_jobs' table."""
    log.info("Starting outbox loop...")
    while not shutdown_requested:
        try:
            job = worker_utils.claim_outbox_job()
            if job:
                job_id = job["id"]
                log.info("Processing outbox job %s (transport: %s)", job_id, job.get("transport"))
                
                try:
                    await execute_outbox_job(job)
                    worker_utils.update_job_status("outbox_jobs", job_id, "sent")
                    log.info("Successfully processed outbox job %s", job_id)
                except Exception as e:
                    log.error("Failed to process outbox job %s: %s", job_id, e)
                    worker_utils.update_job_status("outbox_jobs", job_id, "failed", error=str(e))
                
                continue # Check for more jobs immediately
            
            await asyncio.sleep(1)
        except Exception as e:
            log.error("Error in outbox_loop: %s", e)
            await asyncio.sleep(5)

async def main() -> None:
    """Main entry point for the worker process."""
    # Pre-register jobs so they are available for --list-jobs
    register_scheduled_jobs()

    if "--list-jobs" in sys.argv:
        for job in _scheduler.get_jobs():
            print(f"Job: {job.id}, Trigger: {job.trigger}")
        return

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

    if "--test-outbox" in sys.argv:
        log.info("Test-outbox requested. Simulating an outbox job...")
        database.validate_schema()
        mock_recipient = "972591234567"
        mock_payload = {"type": "text", "body": "This is a test outbox message."}
        database.execute(
            "INSERT INTO outbox_jobs (transport, recipient, payload, status) VALUES ('whatsapp_meta', %s, %s, 'pending')",
            (mock_recipient, json.dumps(mock_payload))
        )
        # Run one iteration of outbox_loop logic manually
        job = worker_utils.claim_outbox_job()
        if job:
            try:
                await execute_outbox_job(job)
                worker_utils.update_job_status("outbox_jobs", job["id"], "sent")
                log.info("Test-outbox: Successfully processed mock job.")
            except Exception as e:
                log.error("Test-outbox: Failed to process mock job: %s", e)
                worker_utils.update_job_status("outbox_jobs", job["id"], "failed", error=str(e))
        else:
            log.error("Test-outbox: Failed to claim the mock job.")
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

    # Start Scheduler
    _scheduler.start()
    log.info(
        "Scheduler started — backups at 3am, retention at 4am, follow-up every 6h, monthly report on 1st, retry queue every 15min"
    )

    # Run inbox and outbox loops concurrently
    try:
        await asyncio.gather(
            inbox_loop(),
            outbox_loop()
        )
    finally:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler shut down.")
    
    log.info("Worker stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
