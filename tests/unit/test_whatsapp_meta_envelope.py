import json
from pathlib import Path
import pytest
from app.routers.whatsapp import _parse_meta_envelope

DATA = Path(__file__).resolve().parents[1] / "data"

def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)

class TestMetaEnvelopeParser:
    def test_text_message_parses(self):
        body = _load("meta_webhook_text.json")
        out = _parse_meta_envelope(body)
        assert out == [("972599123456", "menu", "فاطمة")]

    def test_button_reply_maps_to_command(self):
        body = _load("meta_webhook_button_reply.json")
        out = _parse_meta_envelope(body)
        assert len(out) == 1
        assert out[0][1] == "confirm"

    def test_list_reply_parses(self):
        body = _load("meta_webhook_list_reply.json")
        out = _parse_meta_envelope(body)
        assert len(out) == 1
        assert out[0][1] == "prod_1"

    def test_status_callback_noop(self):
        body = _load("meta_webhook_status.json")
        out = _parse_meta_envelope(body)
        assert out == []

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
                            "type": "image",
                            "image": {"id": "123"}
                        }]
                    }
                }]
            }]
        }
        out = _parse_meta_envelope(body)
        assert out == []

    def test_malformed_payload_is_safe(self):
        assert _parse_meta_envelope({}) == []
        assert _parse_meta_envelope({"object": "whatsapp_business_account"}) == []
        assert _parse_meta_envelope({"object": "whatsapp_business_account", "entry": [{}]}) == []
