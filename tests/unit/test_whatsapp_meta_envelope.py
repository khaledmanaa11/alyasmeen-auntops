import json
from pathlib import Path

from app.services.transport import parse_meta_envelope as _parse_meta_envelope

DATA = Path(__file__).parent.parent / "data"


def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


class TestMetaEnvelopeParser:
    def test_text_message_parses(self):
        body = _load("meta_webhook_text.json")
        out = _parse_meta_envelope(body)
        assert len(out) == 1
        assert out[0]["from"] == "972599123456"
        assert out[0]["type"] == "message"
        assert out[0]["payload"]["text"]["body"] == "menu"

    def test_button_reply_maps_to_command(self):
        body = _load("meta_webhook_button_reply.json")
        out = _parse_meta_envelope(body)
        assert len(out) == 1
        assert out[0]["type"] == "message"
        assert out[0]["payload"]["interactive"]["button_reply"]["id"] == "confirm"

    def test_list_reply_parses(self):
        body = _load("meta_webhook_list_reply.json")
        out = _parse_meta_envelope(body)
        assert len(out) == 1
        assert out[0]["type"] == "message"
        assert out[0]["payload"]["interactive"]["list_reply"]["id"] == "prod_1"

    def test_status_callback_noop(self):
        body = _load("meta_webhook_status.json")
        out = _parse_meta_envelope(body)
        assert len(out) == 1
        assert out[0]["type"] == "status"
        assert out[0]["status"] == "delivered"

    def test_unsupported_type_noop(self):
        # Inline image-type envelope
        body = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messages": [{
                            "from": "972599123456",
                            "id": "wamid.123",
                            "type": "image",
                            "image": {"id": "123"}
                        }]
                    }
                }]
            }]
        }
        out = _parse_meta_envelope(body)
        assert len(out) == 1
        assert out[0]["type"] == "message"
        assert out[0]["payload"]["type"] == "image"

        assert _parse_meta_envelope({}) == []
        assert _parse_meta_envelope({"object": "whatsapp_business_account"}) == []
        assert _parse_meta_envelope({"object": "whatsapp_business_account", "entry": [{}]}) == []
