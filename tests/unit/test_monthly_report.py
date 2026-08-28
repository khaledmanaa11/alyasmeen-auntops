"""
test_monthly_report.py — Unit tests for app/services/monthly_report.py

Tests report text generation, previous-month calculation, and snapshot saving
with a fully mocked database — no real Supabase calls.
"""
import pytest


@pytest.fixture(autouse=True)
def mock_whatsapp(monkeypatch):
    """Patch queue_text so no real WhatsApp call is made."""
    import app.services.monthly_report as mr

    monkeypatch.setattr(mr, "queue_text", lambda to, msg: None)


@pytest.fixture()
def mock_db(monkeypatch):
    """Patch query/execute in monthly_report so no real DB call is made."""
    import app.services.monthly_report as mr

    def fake_query(sql, params=()):
        if "total_orders" in sql:
            return [{"total_orders": 15, "total_revenue": 750.0}]
        if "product_name" in sql:
            return [
                {"product_name": "كريم اليدين", "total_qty": 8},
                {"product_name": "لوشن الجسم", "total_qty": 5},
            ]
        if "COUNT" in sql and "customers" in sql:
            return [{"count": 30}]
        if "TO_CHAR" in sql:
            return [{"day": "2026-02-15", "count": 3}]
        if "GROUP BY status" in sql:
            return [{"status": "done", "count": 10}]
        if "SUM" in sql and "revenue" in sql.lower():
            return [{"product_name": "كريم", "total_qty": 5, "revenue": 125.0}]
        return []

    def fake_execute(sql, params=()):
        pass

    monkeypatch.setattr(mr, "query", fake_query)
    monkeypatch.setattr(mr, "execute", fake_execute)
    return fake_query


class TestPreviousMonth:
    def test_returns_two_dates(self):
        from app.services.monthly_report import _previous_month

        first_day, last_day = _previous_month()
        assert first_day.day == 1
        assert last_day >= first_day

    def test_first_day_is_first_of_month(self):
        from app.services.monthly_report import _previous_month

        first_day, _ = _previous_month()
        assert first_day.day == 1

    def test_last_day_matches_month(self):
        import calendar

        from app.services.monthly_report import _previous_month

        first_day, last_day = _previous_month()
        _, days_in_month = calendar.monthrange(last_day.year, last_day.month)
        assert last_day.day == days_in_month


class TestBuildReport:
    def test_returns_non_empty_string(self, mock_db):
        from app.services.monthly_report import build_report

        report = build_report(2026, 2)
        assert isinstance(report, str)
        assert len(report) > 0

    def test_contains_month_name(self, mock_db):
        from app.services.monthly_report import build_report

        report = build_report(2026, 3)  # March
        assert "مارس" in report

    def test_contains_order_count(self, mock_db):
        from app.services.monthly_report import build_report

        report = build_report(2026, 2)
        assert "15" in report

    def test_contains_top_products(self, mock_db):
        from app.services.monthly_report import build_report

        report = build_report(2026, 2)
        assert "كريم اليدين" in report

    def test_no_products_shows_empty_message(self, monkeypatch):
        import app.services.monthly_report as mr

        def no_products(sql, params=()):
            if "total_orders" in sql:
                return [{"total_orders": 0, "total_revenue": 0.0}]
            return []

        monkeypatch.setattr(mr, "query", no_products)
        report = mr.build_report(2026, 2)
        assert "لا توجد" in report


class TestSendMonthlyReport:
    def test_skips_when_aunt_phone_not_set(self, mock_db, monkeypatch):
        import app.services.config as cfg
        import app.services.monthly_report as mr

        monkeypatch.setattr(cfg.Config, "AUNT_PHONE", None)
        sent = []
        monkeypatch.setattr(mr, "queue_text", lambda to, msg: sent.append(to))
        mr.send_monthly_report()
        assert sent == []

    def test_sends_to_aunt_phone(self, mock_db, monkeypatch):
        import app.services.config as cfg
        import app.services.monthly_report as mr

        monkeypatch.setattr(cfg.Config, "AUNT_PHONE", "972591111111")
        sent = []
        monkeypatch.setattr(mr, "queue_text", lambda to, msg: sent.append(to))
        mr.send_monthly_report()
        assert "972591111111" in sent


class TestArabicMonths:
    def test_all_12_months_present(self):
        from app.services.monthly_report import _AR_MONTHS

        # Index 1..12
        assert len(_AR_MONTHS) == 13  # index 0 is empty string
        assert _AR_MONTHS[0] == ""
        assert _AR_MONTHS[1] == "يناير"
        assert _AR_MONTHS[12] == "ديسمبر"
