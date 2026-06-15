"""
test_retry_actions_pdf.py — Additional tests for the pdf_invoice action path
in app/services/retry_actions.py to boost coverage of lines 38-73.
"""


import os
os.environ["USE_MOCK_WHATSAPP"] = "1"

class TestPdfInvoiceAction:
    def test_pdf_invoice_sends_document(self, monkeypatch):
        import app.services.retry_actions as ra
        import app.services.whatsapp_dev as dev
        import app.services.whatsapp_meta as meta

        documents_sent = []

        def fake_query(sql, params=()):
            if "customers" in sql:
                return [{"id": 5, "phone": "972591234567", "customer_name": "فاطمة"}]
            if "order_lines" in sql:
                return [{"product_name": "كريم", "qty": 1, "unit_price": 25.0}]
            return []

        def fake_send_doc(to, pdf_bytes, filename, caption=None):
            documents_sent.append({"to": to, "filename": filename})
            return {"dev": True}

        monkeypatch.setattr(ra, "query", fake_query)
        monkeypatch.setattr(dev, "send_document_bytes", fake_send_doc)
        monkeypatch.setattr(meta, "send_document_bytes", fake_send_doc)

        ra.execute_action("pdf_invoice", order_id=5, phone="972591234567")
        assert len(documents_sent) == 1
        assert documents_sent[0]["to"] == "972591234567"
        assert ".pdf" in documents_sent[0]["filename"]

    def test_pdf_invoice_with_no_order_rows(self, monkeypatch):
        import app.services.retry_actions as ra
        import app.services.whatsapp_dev as dev
        import app.services.whatsapp_meta as meta

        documents_sent = []

        def fake_query(sql, params=()):
            if "customers" in sql:
                return []  # no order rows
            return [{"product_name": "test", "qty": 1, "unit_price": 10.0}]

        monkeypatch.setattr(ra, "query", fake_query)
        monkeypatch.setattr(dev, "send_document_bytes",
                            lambda to, b, filename, caption=None: documents_sent.append(to) or {})
        monkeypatch.setattr(meta, "send_document_bytes",
                            lambda to, b, filename, caption=None: documents_sent.append(to) or {})

        ra.execute_action("pdf_invoice", order_id=99, phone="972591234567")
        assert len(documents_sent) == 1  # still sends even without customer name
