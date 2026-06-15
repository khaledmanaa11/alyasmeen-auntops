"""
test_followup.py — Unit tests for app/services/followup.py

Tests record_delivery (DB insert) and send_followups (query + send + mark sent).
All DB and WhatsApp calls are mocked.
"""
import pytest


@pytest.fixture(autouse=True)
def mock_whatsapp(monkeypatch):
    import app.services.followup as fu

    monkeypatch.setattr(fu, "enqueue_outbox", lambda to, payload: None)


class TestRecordDelivery:
    def test_inserts_followup_row(self, monkeypatch):
        import app.services.followup as fu

        calls = []
        monkeypatch.setattr(fu, "execute", lambda sql, params=(): calls.append(params))

        fu.record_delivery("972591234567", "42")
        assert len(calls) == 1
        assert "972591234567" in calls[0]
        assert "42" in calls[0]


class TestSendFollowups:
    def test_no_pending_followups_returns_zero(self, monkeypatch):
        import app.services.followup as fu

        monkeypatch.setattr(fu, "query", lambda sql, params=(): [])
        result = fu.send_followups()
        assert result == 0

    def test_sends_message_to_each_customer(self, monkeypatch):
        import app.services.followup as fu

        pending = [
            {"id": 1, "phone": "972591111111", "order_id": "10"},
            {"id": 2, "phone": "972592222222", "order_id": "11"},
        ]
        sent = []
        monkeypatch.setattr(fu, "query", lambda sql, params=(): pending)
        monkeypatch.setattr(fu, "execute", lambda sql, params=(): None)
        monkeypatch.setattr(fu, "enqueue_outbox", lambda to, payload: sent.append(to))

        result = fu.send_followups()
        assert result == 2
        assert "972591111111" in sent
        assert "972592222222" in sent

    def test_marks_followup_as_sent(self, monkeypatch):
        import app.services.followup as fu

        pending = [{"id": 5, "phone": "972591234567", "order_id": "20"}]
        execute_calls = []
        monkeypatch.setattr(fu, "query", lambda sql, params=(): pending)
        monkeypatch.setattr(fu, "execute", lambda sql, params=(): execute_calls.append(params))
        monkeypatch.setattr(fu, "enqueue_outbox", lambda to, payload: None)

        fu.send_followups()
        # Should have called execute to mark sent=TRUE
        assert any(5 in (p or ()) for p in execute_calls)

    def test_continues_on_send_failure(self, monkeypatch):
        import app.services.followup as fu

        pending = [
            {"id": 1, "phone": "972591111111", "order_id": "10"},
            {"id": 2, "phone": "972592222222", "order_id": "11"},
        ]
        call_count = [0]

        def flaky_send(to, payload):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("network error")

        monkeypatch.setattr(fu, "query", lambda sql, params=(): pending)
        monkeypatch.setattr(fu, "execute", lambda sql, params=(): None)
        monkeypatch.setattr(fu, "enqueue_outbox", flaky_send)

        result = fu.send_followups()
        assert result == 1  # only one succeeded
