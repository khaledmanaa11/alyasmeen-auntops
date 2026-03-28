"""
Hebrew PDF Invoice Generator — replaces page_wave invoicing.

Generates a standard Israeli חשבונית מס/קבלה as a PDF (bytes) using fpdf2.
Hebrew text is rendered RTL via python-bidi.

# noqa: file-too-long
This file is a layout-heavy PDF renderer. The layout logic (header, meta rows,
RTL table columns, footer) is tightly coupled and cannot be cleanly split into
separate files without losing readability. Keeping it in one file is intentional.
"""
from __future__ import annotations

import logging
from pathlib import Path

from bidi.algorithm import get_display
from fpdf import FPDF

logger = logging.getLogger(__name__)

FONT_PATH = Path(__file__).parent.parent / "data" / "fonts" / "Heebo-Regular.ttf"

# Shekel sign — plain text fallback since some fonts render ₪ inconsistently
SHEKEL = "ILS"


def _h(text: str) -> str:
    """Apply BiDi algorithm so fpdf2 renders Hebrew text right-to-left."""
    if not text:
        return ""
    return get_display(str(text))


def generate_invoice_pdf(
    order_id: int,
    customer_name: str,
    order_date: str,
    lines: list[dict],
    total: float,
) -> bytes:
    """
    Generate a Hebrew PDF invoice (Israeli חשבונית format) and return it as bytes.

    Args:
        order_id:      Integer order ID (e.g. 8 → displayed as ORD-0008)
        customer_name: Customer's name
        order_date:    Date string formatted as "DD/MM/YYYY"
        lines:         List of dicts with keys: product_name, qty, unit_price
        total:         Order total as float

    Returns:
        PDF file as bytes.
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    pdf.add_font("Heebo", "", str(FONT_PATH))

    page_w = pdf.w - pdf.l_margin - pdf.r_margin   # usable width
    order_label = f"ORD-{order_id:04d}"

    # ── Header ────────────────────────────────────────────────────────────────
    pdf.set_font("Heebo", size=22)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(page_w, 10, "ALYASMEEN", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Heebo", size=11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(page_w, 6, _h("טיפוח טבעי — עבודת יד"), align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(4)

    # ── Invoice meta ─────────────────────────────────────────────────────────
    pdf.set_font("Heebo", size=14)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(page_w, 8, _h("חשבונית מס / קבלה"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Heebo", size=10)
    pdf.set_text_color(60, 60, 60)

    def meta_row(label_heb: str, value: str) -> None:
        """Print one right-aligned label: value row."""
        text = _h(f"{label_heb}: {value}")
        pdf.cell(page_w, 6, text, align="R", new_x="LMARGIN", new_y="NEXT")

    meta_row("מספר הזמנה", order_label)
    meta_row("תאריך", order_date)
    meta_row("לכבוד", customer_name or _h("לקוח יקר"))

    pdf.ln(4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(4)

    # ── Table header ─────────────────────────────────────────────────────────
    # Columns (RTL order on page): פריט | כמות | מחיר ליחידה | סה"כ
    col_total  = 30
    col_price  = 35
    col_qty    = 20
    col_name   = page_w - col_total - col_price - col_qty

    pdf.set_font("Heebo", size=10)
    pdf.set_fill_color(245, 245, 245)
    pdf.set_text_color(30, 30, 30)

    # Draw header cells right-to-left (fpdf always moves left-to-right, so we
    # lay out the columns in visual-RTL order: total | price | qty | name)
    x_start = pdf.l_margin
    y = pdf.get_y()
    row_h = 7

    def header_cell(w: float, label: str) -> None:
        pdf.set_xy(x_start + page_w - pdf.get_x() + pdf.l_margin - w, y)  # noqa: F841 — unused; positioning done below

    # Simpler approach: place each cell manually from right to left
    def rtl_row(items: list[tuple[float, str]], y_pos: float, fill: bool = False, bold: bool = False) -> None:
        """Draw a row of cells right-to-left. items = [(width, text), ...]"""
        x = pdf.l_margin + page_w  # start from right edge
        for w, txt in items:
            x -= w
            pdf.set_xy(x, y_pos)
            pdf.cell(w, row_h, txt, border=1, align="C", fill=fill,
                     new_x="RIGHT", new_y="TOP")
        pdf.ln(row_h)
        pdf.set_xy(pdf.l_margin, y_pos + row_h)

    header_items = [
        (col_total, _h('סה"כ')),
        (col_price, _h("מחיר ליחידה")),
        (col_qty,   _h("כמות")),
        (col_name,  _h("פריט")),
    ]
    rtl_row(header_items, y, fill=True)

    # ── Table rows ───────────────────────────────────────────────────────────
    pdf.set_fill_color(255, 255, 255)
    pdf.set_font("Heebo", size=10)

    for i, line in enumerate(lines):
        name       = str(line.get("product_name") or "")
        qty        = int(line.get("qty") or 1)
        unit_price = float(line.get("unit_price") or 0)
        line_total = qty * unit_price

        row_items = [
            (col_total, f"{line_total:.2f} {SHEKEL}"),
            (col_price, f"{unit_price:.2f} {SHEKEL}"),
            (col_qty,   str(qty)),
            (col_name,  _h(name)),
        ]
        fill = (i % 2 == 1)
        if fill:
            pdf.set_fill_color(250, 250, 250)
        rtl_row(row_items, pdf.get_y(), fill=fill)
        pdf.set_fill_color(255, 255, 255)

    # ── Total row ────────────────────────────────────────────────────────────
    pdf.ln(2)
    pdf.set_font("Heebo", size=11)
    pdf.set_text_color(30, 30, 30)
    total_text = _h(f'סה"כ לתשלום: {total:.2f} {SHEKEL}')
    pdf.cell(page_w, 8, total_text, align="R", new_x="LMARGIN", new_y="NEXT")

    # ── Footer ───────────────────────────────────────────────────────────────
    pdf.ln(6)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(4)

    pdf.set_font("Heebo", size=10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(page_w, 6, _h("תודה על הקנייה! אנחנו שמחים לשרת אותך."), align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(page_w, 6, "ALYASMEEN", align="C", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
