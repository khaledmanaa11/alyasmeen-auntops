import time
import structlog
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from app.services.config import Config
from app.shared.logging import setup_logging

# Initialize structured logging
setup_logging()
logger = structlog.get_logger(__name__)

def start_worker():
    logger.info("Starting worker process")
    
    # Configure JobStore
    jobstores = {}
    if Config.DATABASE_URL:
        # APScheduler needs the DB URL
        jobstores['default'] = SQLAlchemyJobStore(url=Config.DATABASE_URL)
        logger.info("Using SQLAlchemyJobStore", db_host=Config.DATABASE_URL.split('@')[-1] if '@' in Config.DATABASE_URL else "local")
    else:
        logger.warning("DATABASE_URL not set, using MemoryJobStore (non-persistent)")

    scheduler = BlockingScheduler(jobstores=jobstores)

    # Import jobs
    from app.services.followup import send_followups
    from app.services.monthly_report import send_monthly_report    
    from app.services.retry_queue import process_retries
    from app.services.processor import process_webhook_events, process_outbox_jobs

    # Scheduled Jobs
    scheduler.add_job(send_followups, "interval", hours=6, id="followup", replace_existing=True)
    scheduler.add_job(send_monthly_report, "cron", day=1, hour=8, minute=0, id="monthly_report", replace_existing=True)
    scheduler.add_job(process_retries, "interval", minutes=15, id="retry_queue", replace_existing=True)

    # Polling Jobs
    scheduler.add_job(process_webhook_events, "interval", seconds=3, id="webhook_processor", replace_existing=True)
    scheduler.add_job(process_outbox_jobs, "interval", seconds=2, id="outbox_processor", replace_existing=True)

    logger.info(
        "Worker scheduler initialized",
        jobs=["followup", "monthly_report", "retry_queue", "webhook_processor", "outbox_processor"],        
        interval_webhook="3s",
        interval_outbox="2s"
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped")
    except Exception as e:
        logger.error("Worker crashed", error=str(e))
        raise

if __name__ == "__main__":
    start_worker()
