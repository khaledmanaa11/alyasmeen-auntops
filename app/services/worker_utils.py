import logging
from typing import Any, Dict, Optional

from app.db import database

log = logging.getLogger(__name__)

def claim_inbox_event() -> Optional[Dict[str, Any]]:
    """Atomically claim one pending webhook event using the Supabase RPC."""
    try:
        rows = database.query("SELECT * FROM claim_webhook_event()")
        return rows[0] if rows else None
    except Exception as e:
        log.error("worker_utils: failed to claim inbox event: %s", e)
        return None

def claim_outbox_job() -> Optional[Dict[str, Any]]:
    """Atomically claim one pending outbox job using the Supabase RPC."""
    try:
        rows = database.query("SELECT * FROM claim_outbox_job()")
        return rows[0] if rows else None
    except Exception as e:
        log.error("worker_utils: failed to claim outbox job: %s", e)
        return None

def update_job_status(table: str, job_id: int, status: str, error: Optional[str] = None) -> None:
    """Update the status (and optionally error) of a job in the specified table."""
    if table not in ("webhook_events", "outbox_jobs"):
        raise ValueError(f"Invalid table for status update: {table}")
        
    try:
        if error:
            database.execute(
                f"UPDATE {table} SET status = %s, error = %s WHERE id = %s",
                (status, error, job_id)
            )
        else:
            database.execute(
                f"UPDATE {table} SET status = %s WHERE id = %s",
                (status, job_id)
            )
    except Exception as e:
        log.error("worker_utils: failed to update status for %s:%s: %s", table, job_id, e)
