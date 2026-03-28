import os
import pathlib
import random
import sys

from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MOCK_WHATSAPP"] = "1"

import app.routers.whatsapp as wa  # noqa: E402
from app.main import app  # noqa: E402

FAKE_CATALOG = [
    {"id": 1, "name": "تمر ممتاز", "list_price": 10.0, "description_sale": "تمر طبيعي فاخر"},
    {"id": 2, "name": "عسل طبيعي", "list_price": 20.0, "description_sale": "عسل نحل بلدي"},
]


def test_quantity_pattern_adds_to_cart(monkeypatch):
    """'2x1' pattern should add 2 units of product 1 to cart."""
    monkeypatch.setattr(wa, "_CATALOG", FAKE_CATALOG)

    phone = f"1557{random.randint(100000, 999999)}"
    client = TestClient(app)

    # Show menu so menu_products is populated in session
    r1 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
    assert r1.status_code == 200

    # Add product 1 with qty 2
    r2 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "2x1"})
    assert r2.status_code == 200
    txt = r2.json().get("text", "")
    assert "تمر ممتاز" in txt
    assert "× 2" in txt


def test_cart_empty_view_add_then_clear(monkeypatch):
    """Full cart lifecycle: empty → add → view → clear → empty again."""
    monkeypatch.setattr(wa, "_CATALOG", FAKE_CATALOG)

    phone = f"1558{random.randint(100000, 999999)}"
    client = TestClient(app)

    # Empty cart view
    r_empty = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "cart"})
    assert r_empty.status_code == 200
    assert "فارغة" in r_empty.json().get("text", "")

    # Show menu then add product 1
    client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
    client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})

    # Cart should now contain the product
    r_cart = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "cart"})
    assert r_cart.status_code == 200
    txt = r_cart.json().get("text", "")
    assert "تمر ممتاز" in txt
    assert "الإجمالي" in txt

    # Clear cart
    r_clear = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "clear"})
    assert r_clear.status_code == 200

    # Cart should be empty again
    r_cart2 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "cart"})
    assert r_cart2.status_code == 200
    assert "فارغة" in r_cart2.json().get("text", "")
