import hmac
import hashlib
import json
from unittest.mock import patch
from app.services.transport import verify_meta_signature, parse_meta_envelope

def test_verify_meta_signature_valid():
    secret = "test_secret"
    body = b"hello world"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    
    with patch("app.services.transport.Config.WA_META_APP_SECRET", secret):
        assert verify_meta_signature(body, signature) is True

def test_verify_meta_signature_invalid():
    secret = "test_secret"
    body = b"hello world"
    signature = "sha256=invalid"
    
    with patch("app.services.transport.Config.WA_META_APP_SECRET", secret):
        assert verify_meta_signature(body, signature) is False

def test_verify_meta_signature_missing_header():
    secret = "test_secret"
    body = b"hello world"
    
    with patch("app.services.transport.Config.WA_META_APP_SECRET", secret):
        assert verify_meta_signature(body, "") is False
        assert verify_meta_signature(body, None) is False

def test_parse_meta_envelope_message():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "123456789",
                        "id": "wamid.HBgMOTcyNTkyNzE2MDY3FQIAERgSRjBDM0VFOTRBN0NBMDRCNzY1AA==",
                        "timestamp": "1622117133",
                        "text": {"body": "hi"},
                        "type": "text"
                    }]
                }
            }]
        }]
    }
    
    events = parse_meta_envelope(payload)
    assert len(events) == 1
    assert events[0]["wamid"] == "wamid.HBgMOTcyNTkyNzE2MDY3FQIAERgSRjBDM0VFOTRBN0NBMDRCNzY1AA=="
    assert events[0]["from"] == "123456789"
    assert events[0]["type"] == "message"

def test_parse_meta_envelope_status():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{
                        "id": "wamid.ID",
                        "recipient_id": "123456789",
                        "status": "delivered",
                        "timestamp": "1622117133"
                    }]
                }
            }]
        }]
    }
    
    events = parse_meta_envelope(payload)
    assert len(events) == 1
    assert events[0]["wamid"] == "wamid.ID"
    assert events[0]["status"] == "delivered"
    assert events[0]["type"] == "status"

def test_parse_meta_envelope_empty():
    assert parse_meta_envelope({}) == []
    assert parse_meta_envelope({"entry": []}) == []
