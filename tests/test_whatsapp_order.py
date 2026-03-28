import os
import pathlib
import random
import sys

from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Ensure project root (auntops_fixed) is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load env
load_dotenv()

# If running from repo root, also try project .env
here = os.path.dirname(__file__)
proj_env = os.path.join(os.path.dirname(here), ".env")
if os.path.isfile(proj_env):
    load_dotenv(proj_env)


def _maybe_verify_sheet(order_id: int) -> bool | None:
    """Best-effort verification in Google Sheets/AppSheet tab.
    Returns True if found, False if not found, or None if not configured.
    """
    try:
        import gspread  # type: ignore

        from app.services.config import Config
        ss_id = getattr(Config, "GSPREAD_SPREADSHEET_ID", None)
        svc = getattr(Config, "GSPREAD_SERVICE_ACCOUNT_FILE", None)
        tab = getattr(Config, "SHEET_TAB_ORDERS", "Orders To Do")
        if not (ss_id and svc and os.path.isfile(svc)):
            return None
        gc = gspread.service_account(filename=svc)
        sh = gc.open_by_key(ss_id)
        ws = sh.worksheet(tab)
        rows = ws.get_all_records()  # list of dicts keyed by headers
        for r in rows:
            oid = r.get("order_id")
            if str(oid) == str(order_id):
                return True
        return False
    except Exception:
        return None


def test_whatsapp_order_flow_creates_order():
    os.environ["USE_MOCK_WHATSAPP"] = "1"

    from app.main import app
    client = TestClient(app)

    phone = f"1555{random.randint(100000, 999999)}"

    # Step 1: Load menu to enable numeric selection
    r1 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "menu"})
    assert r1.status_code == 200

    # Step 2: Choose first product
    r2 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "1"})
    assert r2.status_code == 200

    # Step 3: Confirm order
    r3 = client.post("/whatsapp/webhook", json={"from_number": phone, "text": "confirm"})
    assert r3.status_code == 200
    data = r3.json()
    assert data.get("ok") is True
    order_id = data.get("order_id")
    order_name = data.get("order_name")
    assert isinstance(order_id, int) and order_id > 0
    assert order_name and order_name.startswith("ORD-")
