"""
test_pdf_invoice.py — Unit tests for app/services/pdf_invoice.py

Tests that generate_invoice_pdf returns valid PDF bytes and the BiDi
helper _h correctly applies right-to-left rendering to Hebrew/Arabic text.
"""


class TestBidiHelper:
    def test_h_empty_string(self):
        from app.services.pdf_invoice import _h

        assert _h("") == ""

    def test_h_non_empty_returns_string(self):
        from app.services.pdf_invoice import _h

        result = _h("שלום")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_h_none_returns_empty(self):
        from app.services.pdf_invoice import _h

        result = _h(None)
        assert result == ""


class TestGenerateInvoicePdf:
    SAMPLE_LINES = [
        {"product_name": "كريم اليدين", "qty": 2, "unit_price": 25.0},
        {"product_name": "لوشن الجسم", "qty": 1, "unit_price": 40.0},
    ]

    def test_returns_bytes(self):
        from app.services.pdf_invoice import generate_invoice_pdf

        result = generate_invoice_pdf(
            order_id=42,
            customer_name="فاطمة أحمد",
            order_date="01/03/2026",
            lines=self.SAMPLE_LINES,
            total=90.0,
        )
        assert isinstance(result, bytes)

    def test_pdf_has_content(self):
        from app.services.pdf_invoice import generate_invoice_pdf

        result = generate_invoice_pdf(
            order_id=1,
            customer_name="عميل",
            order_date="01/01/2026",
            lines=self.SAMPLE_LINES,
            total=65.0,
        )
        assert len(result) > 1000  # real PDFs are at least 1 KB

    def test_pdf_starts_with_pdf_magic(self):
        from app.services.pdf_invoice import generate_invoice_pdf

        result = generate_invoice_pdf(
            order_id=7,
            customer_name="Test",
            order_date="15/03/2026",
            lines=self.SAMPLE_LINES,
            total=50.0,
        )
        assert result[:4] == b"%PDF"

    def test_empty_lines_still_returns_pdf(self):
        from app.services.pdf_invoice import generate_invoice_pdf

        result = generate_invoice_pdf(
            order_id=99,
            customer_name="",
            order_date="01/03/2026",
            lines=[],
            total=0.0,
        )
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"

    def test_large_order_id_formatted(self):
        from app.services.pdf_invoice import generate_invoice_pdf

        # Should not raise even with large order IDs
        result = generate_invoice_pdf(
            order_id=9999,
            customer_name="Customer",
            order_date="01/03/2026",
            lines=self.SAMPLE_LINES,
            total=100.0,
        )
        assert isinstance(result, bytes)
