"""
test_retry.py — Unit tests for retry_queue.py and retry_actions.py

Tests enqueue, process_retries, and individual action dispatch,
all with fully mocked DB and WhatsApp sender.
"""
import pytest


@pytest.fixture(autouse=True)
def mock_whatsapp_sender(monkeypatch):
    """Patch send_text in whatsapp_dev so no console output during tests."""
    import app.services.whatsapp_dev as dev

    monkeypatch.setattr(dev, "send_text", lambda to, msg: {"dev": True})


# ---------------------------------------------------------------------------
# retry_queue tests
# ---------------------------------------------------------------------------

class TestEnqueue:
    def test_enqueue_inserts_row(self, monkeypatch):
        import app.services.retry_queue as rq

        calls = []
        monkeypatch.setattr(rq, "execute", lambda sql, params=(): calls.append(params))

        rq.enqueue("send_text_ready", order_id=5, phone="972591234567")
        assert len(calls) == 1
        assert "send_text_ready" in calls[0]
        assert 5 in calls[0]

    def test_enqueue_with_payload(self, monkeypatch):
        import app.services.retry_queue as rq

        calls = []
        monkeypatch.setattr(rq, "execute", lambda sql, params=(): calls.append(params))

        rq.enqueue("pdf_invoice", order_id=3, phone="972591234567", payload={"key": "val"})
        assert len(calls) == 1


class TestProcessRetries:
    def test_empty_queue_returns_zero(self, monkeypatch):
        import app.services.retry_queue as rq

        monkeypatch.setattr(rq, "query", lambda sql, params=(): [])
        result = rq.process_retries()
        assert result == 0

    def test_resolves_successful_action(self, monkeypatch):
        import app.services.retry_queue as rq
        from app.services import retry_actions

        pending = [
            {"id": 1, "action": "send_text_ready", "order_id": 10, "phone": "972591234567", "attempts": 0},
        ]
        monkeypatch.setattr(rq, "query", lambda sql, params=(): pending)
        monkeypatch.setattr(rq, "execute", lambda sql, params=(): None)
        monkeypatch.setattr(retry_actions, "execute_action", lambda action, oid, phone: None)
        # Also patch execute_action in rq module namespace (re-imported)
        monkeypatch.setattr(rq, "execute_action", lambda action, oid, phone: None)

        result = rq.process_retries()
        assert result == 1

    def test_failed_action_increments_attempts(self, monkeypatch):
        import app.services.retry_queue as rq

        pending = [
            {"id": 1, "action": "send_text_ready", "order_id": 10, "phone": "972591234567", "attempts": 0},
        ]
        update_calls = []
        monkeypatch.setattr(rq, "query", lambda sql, params=(): pending)
        monkeypatch.setattr(rq, "execute", lambda sql, params=(): update_calls.append(params))
        monkeypatch.setattr(rq, "execute_action", lambda action, oid, phone: (_ for _ in ()).throw(ConnectionError("fail")))

        result = rq.process_retries()
        assert result == 0
        # Should have called execute to update attempts
        assert len(update_calls) > 0


# ---------------------------------------------------------------------------
# retry_actions tests
# ---------------------------------------------------------------------------

class TestExecuteAction:
    def test_send_text_ready_pickup(self, monkeypatch):
        import app.services.retry_actions as ra
        import app.services.whatsapp_dev as dev

        sent = []
        monkeypatch.setattr(dev, "send_text", lambda to, msg: sent.append(msg) or {})

        def fake_query(sql, params=()):
            return [{"fulfillment": "pickup"}]

        monkeypatch.setattr(ra, "query", fake_query)
        monkeypatch.setattr(ra, "send_text", lambda to, msg: sent.append(msg) or {})

        ra.execute_action("send_text_ready", order_id=5, phone="972591234567")
        assert any("جاهز" in m for m in sent)

    def test_send_text_ready_delivery(self, monkeypatch):
        import app.services.retry_actions as ra

        sent = []

        def fake_query(sql, params=()):
            return [{"fulfillment": "delivery"}]

        monkeypatch.setattr(ra, "query", fake_query)
        monkeypatch.setattr(ra, "send_text", lambda to, msg: sent.append(msg) or {})

        ra.execute_action("send_text_ready", order_id=5, phone="972591234567")
        assert any("طريق" in m for m in sent)

    def test_send_text_done(self, monkeypatch):
        import app.services.retry_actions as ra

        sent = []
        monkeypatch.setattr(ra, "send_text", lambda to, msg: sent.append(msg) or {})

        ra.execute_action("send_text_done", order_id=5, phone="972591234567")
        assert any("شكراً" in m for m in sent)

    def test_send_text_delivered(self, monkeypatch):
        import app.services.retry_actions as ra

        sent = []
        monkeypatch.setattr(ra, "send_text", lambda to, msg: sent.append(msg) or {})

        ra.execute_action("send_text_delivered", order_id=5, phone="972591234567")
        assert any("تم توصيل" in m for m in sent)

    def test_unknown_action_raises(self, monkeypatch):
        import app.services.retry_actions as ra

        with pytest.raises(ValueError, match="unknown action"):
            ra.execute_action("garbage_action", order_id=1, phone="972591234567")
