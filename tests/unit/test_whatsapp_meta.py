"""
test_whatsapp_meta.py — Unit tests for app/services/whatsapp_meta.py

Tests the webhook verification logic (verify_get) and the send_text/
send_document_bytes functions with a mocked requests.post call.
No real Meta API calls are made.

All four senders (send_text, send_buttons, send_document_bytes,
send_document) raise WhatsAppSendError on any non-2xx Meta response instead
of returning the failed status silently — see TestSendFailureRaises — so the
outbox poller's retry logic (app.services.processor.process_job) can catch
the failure and mark the job 'failed' instead of mistaking it for a success.
"""

import pytest


class TestVerifyGet:
    def test_valid_token_returns_200_with_challenge(self, monkeypatch):
        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "WA_META_VERIFY_TOKEN", "my-secret-token")

        ok, code, body = meta.verify_get({
            "hub.mode": "subscribe",
            "hub.verify_token": "my-secret-token",
            "hub.challenge": "abc123",
        })
        assert ok is True
        assert code == 200
        assert body == "abc123"

    def test_wrong_token_returns_403(self, monkeypatch):
        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "WA_META_VERIFY_TOKEN", "correct-token")

        ok, code, body = meta.verify_get({
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "abc123",
        })
        assert ok is False
        assert code == 403

    def test_wrong_mode_returns_403(self, monkeypatch):
        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "WA_META_VERIFY_TOKEN", "token")

        ok, code, _ = meta.verify_get({
            "hub.mode": "unsubscribe",
            "hub.verify_token": "token",
            "hub.challenge": "abc",
        })
        assert ok is False
        assert code == 403

    def test_missing_mode_returns_403(self):
        from app.services.whatsapp_meta import verify_get

        ok, code, _ = verify_get({
            "hub.mode": None,
            "hub.verify_token": None,
            "hub.challenge": "",
        })
        assert ok is False
        assert code == 403


class TestSendTextMockedRequests:
    def test_send_text_in_mock_mode_uses_dev_sender(self, monkeypatch):
        import app.services.config as cfg
        import app.services.whatsapp_dev as dev
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", True)

        sent = []
        monkeypatch.setattr(dev, "send_text", lambda to, msg: sent.append((to, msg)) or {})

        meta.send_text("972591234567", "hello")
        assert len(sent) == 1
        assert sent[0][0] == "972591234567"

    def test_send_text_real_mode_calls_requests(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        fake_response = type("R", (), {
            "status_code": 200,
            "json": lambda self: {"messages": [{"id": "wamid.1"}]},
        })()
        monkeypatch.setattr(requests, "post", lambda *a, **kw: fake_response)

        result = meta.send_text("972591234567", "test message")
        assert result["status"] == 200


class TestWhatsappDev:
    def test_send_text_returns_dict(self):
        from app.services.whatsapp_dev import send_text

        result = send_text("972591234567", "مرحبا")
        assert isinstance(result, dict)
        assert result.get("dev") is True

    def test_send_document_bytes_returns_dict(self):
        from app.services.whatsapp_dev import send_document_bytes

        result = send_document_bytes("972591234567", b"fake-pdf", "test.pdf", "caption")
        assert isinstance(result, dict)
        assert result.get("dev") is True

    def test_send_document_bytes_without_caption(self):
        from app.services.whatsapp_dev import send_document_bytes

        result = send_document_bytes("972591234567", b"fake-pdf", "test.pdf")
        assert isinstance(result, dict)
        assert "caption" not in result

    def test_send_document_returns_dict(self):
        from app.services.whatsapp_dev import send_document

        result = send_document("972591234567", "https://example.com/doc.pdf", "doc.pdf")
        assert isinstance(result, dict)
        assert result.get("dev") is True
        assert result.get("document_link") == "https://example.com/doc.pdf"

    def test_send_document_with_caption(self):
        from app.services.whatsapp_dev import send_document

        result = send_document("972591234567", "https://example.com/doc.pdf", "doc.pdf", "My doc")
        assert result.get("caption") == "My doc"

    def test_verify_get_accepts_any_token(self):
        from app.services.whatsapp_dev import verify_get

        ok, code, challenge = verify_get({
            "hub.mode": "subscribe",
            "hub.verify_token": "anything",
            "hub.challenge": "xyz",
        })
        assert ok is True
        assert code == 200
        assert challenge == "xyz"


class TestSendDocumentBytesMocked:
    def test_send_document_bytes_real_mode(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        upload_resp = type("R", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"id": "media-123"},
        })()
        send_resp = type("R", (), {
            "status_code": 200,
            "json": lambda self: {"messages": [{"id": "wamid.2"}]},
        })()

        call_count = [0]

        def fake_post(*a, **kw):
            call_count[0] += 1
            return upload_resp if call_count[0] == 1 else send_resp

        monkeypatch.setattr(requests, "post", fake_post)

        result = meta.send_document_bytes("972591234567", b"pdf-data", "invoice.pdf", "caption")
        assert result["status"] == 200

    def test_send_document_bytes_real_mode_with_caption(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        upload_resp = type("R", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"id": "media-456"},
        })()
        send_resp = type("R", (), {
            "status_code": 200,
            "json": lambda self: {"messages": [{"id": "wamid.3"}]},
        })()

        call_count = [0]

        def fake_post(*a, **kw):
            call_count[0] += 1
            return upload_resp if call_count[0] == 1 else send_resp

        monkeypatch.setattr(requests, "post", fake_post)
        result = meta.send_document_bytes("972591234567", b"pdf", "doc.pdf")
        assert result["status"] == 200


class TestSendDocumentMocked:
    def test_send_document_real_mode(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        fake_resp = type("R", (), {
            "status_code": 200,
            "json": lambda self: {"messages": [{"id": "wamid.4"}]},
        })()
        monkeypatch.setattr(requests, "post", lambda *a, **kw: fake_resp)

        result = meta.send_document("972591234567", "https://example.com/f.pdf", "f.pdf", "hi")
        assert result["status"] == 200

    def test_send_document_real_mode_no_caption(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "tok")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "999")

        fake_resp = type("R", (), {
            "status_code": 200,
            "json": lambda self: {},
        })()
        monkeypatch.setattr(requests, "post", lambda *a, **kw: fake_resp)

        result = meta.send_document("972591234567", "https://example.com/f.pdf", "f.pdf")
        assert result["status"] == 200


class TestSendFailureRaises:
    """New coverage for the raise-on-failure contract: every sender must
    raise WhatsAppSendError (not just return the failed status dict) when
    the Meta API responds with a non-2xx status."""

    def test_send_text_raises_on_non_2xx(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        fake_response = type("R", (), {
            "status_code": 400,
            "json": lambda self: {"error": {"message": "Invalid parameter"}},
        })()
        monkeypatch.setattr(requests, "post", lambda *a, **kw: fake_response)

        with pytest.raises(meta.WhatsAppSendError):
            meta.send_text("972591234567", "test message")

    def test_send_buttons_raises_on_non_2xx(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        fake_response = type("R", (), {
            "status_code": 500,
            "json": lambda self: {"error": {"message": "Internal error"}},
        })()
        monkeypatch.setattr(requests, "post", lambda *a, **kw: fake_response)

        with pytest.raises(meta.WhatsAppSendError):
            meta.send_buttons("972591234567", "body", [{"id": "a", "title": "A"}])

    def test_send_document_bytes_raises_on_non_2xx(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        upload_resp = type("R", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"id": "media-999"},
        })()
        send_resp = type("R", (), {
            "status_code": 400,
            "json": lambda self: {"error": {"message": "bad request"}},
        })()

        call_count = [0]

        def fake_post(*a, **kw):
            call_count[0] += 1
            return upload_resp if call_count[0] == 1 else send_resp

        monkeypatch.setattr(requests, "post", fake_post)

        with pytest.raises(meta.WhatsAppSendError):
            meta.send_document_bytes("972591234567", b"pdf-data", "invoice.pdf")

    def test_send_document_raises_on_non_2xx(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        fake_resp = type("R", (), {
            "status_code": 403,
            "json": lambda self: {"error": {"message": "forbidden"}},
        })()
        monkeypatch.setattr(requests, "post", lambda *a, **kw: fake_resp)

        with pytest.raises(meta.WhatsAppSendError):
            meta.send_document("972591234567", "https://example.com/f.pdf", "f.pdf")


class TestGatekeeperWiring:
    """Proves send_text's real-mode body actually routes through
    app.shared.gatekeeper.gatekeeper.execute("whatsapp", ...) — not just
    'still works by coincidence' because requests.post is monkeypatched."""

    def test_send_text_raises_rate_limit_exceeded_without_calling_requests(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta
        from app.shared.gatekeeper import RateLimitExceeded

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        called = []
        monkeypatch.setattr(requests, "post", lambda *a, **kw: called.append(1))

        def raising_execute(service, api_call, *args, **kwargs):
            raise RateLimitExceeded(f"{service} rate limit exceeded")

        monkeypatch.setattr(meta.gatekeeper, "execute", raising_execute)

        with pytest.raises(RateLimitExceeded):
            meta.send_text("972591234567", "hello")
        assert called == []

    def test_send_text_calls_gatekeeper_with_whatsapp_service(self, monkeypatch):
        import requests

        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "USE_MOCK_WHATSAPP", False)
        monkeypatch.setattr(cfg.Config, "WA_META_TOKEN", "fake-token")
        monkeypatch.setattr(cfg.Config, "WA_META_PHONE_ID", "123456")

        fake_response = type("R", (), {
            "status_code": 200,
            "json": lambda self: {"messages": [{"id": "wamid.1"}]},
        })()
        monkeypatch.setattr(requests, "post", lambda *a, **kw: fake_response)

        calls = []

        def spy(service, api_call, *args, **kwargs):
            calls.append(service)
            return api_call(*args, **kwargs)

        monkeypatch.setattr(meta.gatekeeper, "execute", spy)

        result = meta.send_text("972591234567", "hello")
        assert result["status"] == 200
        assert calls == ["whatsapp"]


class TestVerifySignature:
    def test_valid_signature(self, monkeypatch):
        import hashlib
        import hmac as hmac_mod
        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "WA_META_APP_SECRET", "secret")

        body = b'{"test": 1}'
        mac = hmac_mod.new(b"secret", body, hashlib.sha256)
        sig = "sha256=" + mac.hexdigest()

        assert meta.verify_signature(body, sig) is True

    def test_invalid_signature_returns_false(self, monkeypatch):
        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "WA_META_APP_SECRET", "secret")

        assert meta.verify_signature(b"body", "sha256=wrong") is False

    def test_missing_secret_returns_false(self, monkeypatch):
        import app.services.config as cfg
        import app.services.whatsapp_meta as meta

        monkeypatch.setattr(cfg.Config, "WA_META_APP_SECRET", None)

        assert meta.verify_signature(b"body", "sha256=abc") is False
