import hmac
import hashlib
import logging
from typing import List, Dict, Any
from app.services.config import Config

log = logging.getLogger(__name__)

def verify_meta_signature(body: bytes, signature: str) -> bool:
    """
    Verify the X-Hub-Signature-256 header sent by Meta.
    Expects signature in format 'sha256=<hash>'.
    """
    if not Config.WA_META_APP_SECRET:
        log.warning("WA_META_APP_SECRET not set. Signature verification bypassed (DANGEROUS).")
        # In a real production environment, we might want to return False here 
        # unless explicitly allowed. For now, we follow the log-and-allow if unset.
        return True
    
    if not signature or not signature.startswith("sha256="):
        log.debug("Signature missing or invalid format")
        return False
    
    try:
        expected_hash = signature.split("sha256=")[1]
        
        actual_hash = hmac.new(
            Config.WA_META_APP_SECRET.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(actual_hash, expected_hash)
    except Exception as e:
        log.error(f"Error verifying Meta signature: {e}")
        return False

def parse_meta_envelope(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract a list of messages and statuses from a Meta Cloud API webhook payload.
    
    Returns a list of simplified event dicts:
    [
        {
            "wamid": "...",
            "type": "message" | "status",
            "from": "...", (for messages)
            "timestamp": "...",
            "payload": { ... original sub-object ... }
        }
    ]
    """
    extracted = []
    
    if not isinstance(payload, dict):
        return extracted
        
    entries = payload.get("entry", [])
    if not isinstance(entries, list):
        return extracted
        
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            
            # Extract Messages
            messages = value.get("messages", [])
            if isinstance(messages, list):
                for msg in messages:
                    extracted.append({
                        "wamid": msg.get("id"),
                        "from": msg.get("from"),
                        "timestamp": msg.get("timestamp"),
                        "type": "message",
                        "payload": msg
                    })
            
            # Extract Statuses (delivery/read receipts)
            statuses = value.get("statuses", [])
            if isinstance(statuses, list):
                for status in statuses:
                    extracted.append({
                        "wamid": status.get("id"),
                        "recipient": status.get("recipient_id"),
                        "timestamp": status.get("timestamp"),
                        "status": status.get("status"),
                        "type": "status",
                        "payload": status
                    })
                
    return extracted
