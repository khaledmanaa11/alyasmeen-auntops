from fastapi.testclient import TestClient

from app.main import app


def test_menu_still_works():
    """
    When sending 'menu', the endpoint should return a product list message.
    """
    client = TestClient(app)
    resp = client.post(
        "/whatsapp/webhook",
        json={"from_number": "+972500000001", "text": "menu"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    # Dev mock sender returns {"dev": True, "to": ..., "text": ...}
    assert data.get("dev") is True
    assert "قائمة المنتجات" in data.get("text", "")


def test_ai_aunt_free_text(monkeypatch):
    """
    Free-text Arabic message should go through AIAunt and return the mocked reply.
    """
    fixed_reply = "أنصحك بالمرطب العلاجي للجسم لأنه مناسب للبشرة الجافة ✨"

    # Patch the AI generate_reply to avoid real API calls
    monkeypatch.setattr(
        "app.routers.whatsapp.ai_generate_reply",
        lambda user_message, previous_messages=None, cart=None, customer_name=None, tool_executor=None: fixed_reply,
    )

    client = TestClient(app)
    resp = client.post(
        "/whatsapp/webhook",
        json={"from_number": "+972500000002", "text": "بشرتي جافة كثير"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # In dev/mock WA sender, response is a dict with text + dev + to
    assert data.get("dev") is True
    assert data.get("to") == "+972500000002"
    assert data.get("text") == fixed_reply
