import json
import logging
from typing import Any, Dict

from app.db import database

log = logging.getLogger(__name__)

def enqueue_outbox(recipient: str, payload: Dict[str, Any], transport: str = "whatsapp_meta") -> int:
    """
    Queue a message or job in the outbox_jobs table for processing by the worker.
    
    Args:
        recipient: The target identifier (e.g., phone number or order ID).
        payload: The data required to execute the job.
        transport: The type of job/transport (e.g., 'whatsapp_meta', 'pdf_generation').
        
    Returns:
        The ID of the newly created outbox job.
    """
    log.info("Queueing outbox job for %s via %s", recipient, transport)
    
    try:
        query = """
            INSERT INTO outbox_jobs (transport, recipient, payload, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING id
        """
        rows = database.query(query, (transport, recipient, json.dumps(payload)))
        if rows:
            return rows[0]["id"]
        raise RuntimeError("Failed to retrieve ID of inserted outbox job")
    except Exception as e:
        log.error("Failed to enqueue outbox job: %s", e)
        raise
