import os
import pathlib
import sys

from fastapi.testclient import TestClient

# Ensure project root on path
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

from app.main import app  # noqa: E402


def test_info_command_uses_catalog(monkeypatch):
    import app.routers.whatsapp as wa

    # Override the catalog with a known test product
    fake_catalog = [{"id": 1, "name": "Ajwa", "list_price": 17.5, "description_sale": "Premium dates.\n500g pack"}]
    monkeypatch.setattr(wa, "_CATALOG", fake_catalog)

    client = TestClient(app)
    phone = "1555000001"

    r1 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
    assert r1.status_code == 200

    r2 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "info 1"})
    assert r2.status_code == 200
    data = r2.json()
    assert isinstance(data, dict) and data.get("dev") is True
    txt = data.get("text", "")
    assert "Ajwa" in txt
    assert "₪" in txt
    assert "Premium dates" in txt
