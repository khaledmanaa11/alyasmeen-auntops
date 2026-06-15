import hmac
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.config import Config
from app.db.database import query, execute

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_webhook_events():
    execute("DELETE FROM webhook_events WHERE id IS NOT NULL")
    yield
    execute("DELETE FROM webhook_events WHERE id IS NOT NULL")

def test_webhook_rejects_missing_signature():
    response = client.post("/whatsapp/webhook", json={"test": "data"})
    assert response.status_code == 403

def test_webhook_rejects_invalid_signature():
    headers = {"X-Hub-Signature-256": "sha256=invalid"}
    response = client.post("/whatsapp/webhook", json={"test": "data"}, headers=headers)
    assert response.status_code == 403

def test_webhook_accepts_valid_signature_and_persists():
    secret = "test_secret"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "123456789",
                        "id": "wamid.TEST_ID_123",
                        "timestamp": "1622117133",
                        "text": {"body": "hi integration test"},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    
    headers = {"X-Hub-Signature-256": signature}
    
    # We need to mock the Config.WA_META_APP_SECRET for the router
    # and ensure it uses the real database.execute instead of the mock from conftest.py
    from unittest.mock import patch
    import app.routers.whatsapp as wa
    with patch("app.services.transport.Config.WA_META_APP_SECRET", secret), \
         patch("app.routers.whatsapp.execute", execute):
        response = client.post("/whatsapp/webhook", content=body, headers=headers)
    
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    
    # Verify persistence
    rows = query("SELECT wamid, status FROM webhook_events WHERE wamid = %s", ("wamid.TEST_ID_123",))
    assert len(rows) == 1
    assert rows[0]["wamid"] == "wamid.TEST_ID_123"
    assert rows[0]["status"] == "pending"

def test_webhook_idempotency():
    secret = "test_secret"
    wamid = "wamid.DUPLICATE_ID"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "123456789",
                        "id": wamid,
                        "timestamp": "1622117133",
                        "text": {"body": "hi duplicate"},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {"X-Hub-Signature-256": signature}
    
    from unittest.mock import patch
    import app.routers.whatsapp as wa
    with patch("app.services.transport.Config.WA_META_APP_SECRET", secret), \
         patch("app.routers.whatsapp.execute", execute):
        # First call
        response1 = client.post("/whatsapp/webhook", content=body, headers=headers)
        assert response1.status_code == 200
        
        # Second call
        response2 = client.post("/whatsapp/webhook", content=body, headers=headers)
        assert response2.status_code == 200
    
    # Verify only one row exists
    rows = query("SELECT id FROM webhook_events WHERE wamid = %s", (wamid,))
    assert len(rows) == 1

def test_webhook_latency():
    import time
    secret = "test_secret"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "123456789",
                        "id": "wamid.LATENCY_TEST",
                        "timestamp": "1622117133",
                        "text": {"body": "latency test"},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {"X-Hub-Signature-256": signature}
    
    from unittest.mock import patch
    with patch("app.services.transport.Config.WA_META_APP_SECRET", secret):
        start = time.time()
        response = client.post("/whatsapp/webhook", content=body, headers=headers)
        duration = time.time() - start
    
    assert response.status_code == 200
    assert duration < 1.0  # Must be fast
