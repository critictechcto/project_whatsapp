"""PDF rendering for plan invoices, built on demand from the invoice's stored snapshot.

Amounts are written as ``INR 2,499.00``: the built-in PDF fonts have no rupee sign.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .gst import GST_STATE_CODES
from .invoices import INDIA_TZ
from .models import Invoice

INK = colors.HexColor("#1b1d1c")
MUTED = colors.HexColor("#6b706d")
LINE = colors.HexColor("#d9dcd9")

BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
SMALL = ParagraphStyle("small", parent=BASE, fontSize=8.5, leading=11, textColor=MUTED)
LABEL = ParagraphStyle("label", parent=SMALL, fontName="Helvetica-Bold", textColor=MUTED)
LABEL_RIGHT = ParagraphStyle("label_right", parent=LABEL, alignment=2)
TITLE = ParagraphStyle("title", parent=BASE, fontName="Helvetica-Bold", fontSize=18, leading=22)
RIGHT = ParagraphStyle("right", parent=BASE, alignment=2)
RIGHT_BOLD = ParagraphStyle("right_bold", parent=RIGHT, fontName="Helvetica-Bold")

FALLBACK_SELLER = "UpChatz"


def format_amount(paise: int) -> str:
    """``INR 1,00,000.00`` with Indian digit grouping."""
    rupees, remainder = divmod(paise, 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"INR {digits}.{remainder:02d}"


def _date(value) -> str:
    return value.astimezone(INDIA_TZ).strftime("%d %b %Y")


def _lines(*parts: str) -> str:
    return "<br/>".join(escape(part) for part in parts if part)


def _seller_block(seller: dict) -> str:
    return _lines(
        seller.get("legal_name") or FALLBACK_SELLER,
        seller.get("address", ""),
        f"GSTIN: {seller['gstin']}" if seller.get("gstin") else "",
    )


def _buyer_block(buyer: dict) -> str:
    state_code = buyer.get("state_code", "")
    state = buyer.get("state_name") or GST_STATE_CODES.get(state_code, "")
    city_line = " ".join(
        part for part in (buyer.get("city", ""), buyer.get("postal_code", "")) if part
    )
    return (
        _lines(
            buyer.get("legal_name", ""),
            buyer.get("address_line1", ""),
            buyer.get("address_line2", ""),
            city_line,
            f"{state} ({state_code})" if state and state_code else state,
            f"GSTIN: {buyer['gstin']}" if buyer.get("gstin") else "",
            buyer.get("email", ""),
        )
        or "-"
    )


def is_tax_invoice(invoice: Invoice) -> bool:
    """A GST tax invoice needs a registered seller; without a GSTIN it is a plain invoice."""
    return bool(invoice.seller.get("gstin"))


def filename(invoice: Invoice) -> str:
    return invoice.number.replace("/", "-") + ".pdf"


def render(invoice: Invoice) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Invoice {invoice.number}",
        author=invoice.seller.get("legal_name") or FALLBACK_SELLER,
    )
    width = doc.width
    story = []

    heading = "Tax invoice" if is_tax_invoice(invoice) else "Invoice"
    meta = _lines(
        f"Invoice no.: {invoice.number}",
        f"Date: {_date(invoice.issued_at)}",
        f"Status: {invoice.get_status_display()}",
    )
    header = Table(
        [[Paragraph(escape(heading), TITLE), Paragraph(meta, RIGHT)]],
        colWidths=[width * 0.5, width * 0.5],
    )
    header.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, 0), 0)])
    )
    story += [header, Spacer(1, 8 * mm)]

    parties = Table(
        [
            [Paragraph("FROM", LABEL), Paragraph("BILL TO", LABEL)],
            [
                Paragraph(_seller_block(invoice.seller), BASE),
                Paragraph(_buyer_block(invoice.buyer), BASE),
            ],
        ],
        colWidths=[width * 0.5, width * 0.5],
    )
    parties.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, -1), 0)])
    )
    story += [parties, Spacer(1, 8 * mm)]

    period = f"{_date(invoice.period_start)} to {_date(invoice.period_end)}"
    rows = [
        [
            Paragraph("DESCRIPTION", LABEL),
            Paragraph("SAC", LABEL),
            Paragraph("AMOUNT", LABEL_RIGHT),
        ],
        [
            Paragraph(_lines(invoice.description, f"Period: {period}"), BASE),
            Paragraph(escape(invoice.sac_code), BASE),
            Paragraph(format_amount(invoice.subtotal_paise), RIGHT),
        ],
    ]
    totals = []
    taxed = invoice.cgst_paise or invoice.sgst_paise or invoice.igst_paise
    if taxed:
        totals.append(("Subtotal", invoice.subtotal_paise))
        if invoice.igst_paise:
            totals.append((f"IGST ({invoice.gst_rate_percent}%)", invoice.igst_paise))
        else:
            half = invoice.gst_rate_percent / 2
            rate = f"{half:g}%"
            totals.append((f"CGST ({rate})", invoice.cgst_paise))
            totals.append((f"SGST ({rate})", invoice.sgst_paise))
    for label, amount in totals:
        rows.append(["", Paragraph(escape(label), RIGHT), Paragraph(format_amount(amount), RIGHT)])
    rows.append(
        [
            "",
            Paragraph("Total", RIGHT_BOLD),
            Paragraph(format_amount(invoice.total_paise), RIGHT_BOLD),
        ]
    )
    items = Table(rows, colWidths=[width * 0.55, width * 0.2, width * 0.25])
    items.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE),
                ("LINEBELOW", (0, 1), (-1, 1), 0.6, LINE),
                ("LINEABOVE", (1, -1), (-1, -1), 0.8, INK),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story += [items, Spacer(1, 8 * mm)]

    notes = []
    if invoice.payment_id:
        provider = invoice.get_payment_provider_display() or "Online payment"
        notes.append(f"Paid via {provider}. Payment ID: {invoice.payment_id}")
    if not taxed:
        notes.append("No GST was charged on this invoice.")
    notes.append("This is a computer-generated invoice and needs no signature.")
    story.append(Paragraph(_lines(*notes), SMALL))

    doc.build(story)
    return buffer.getvalue()
