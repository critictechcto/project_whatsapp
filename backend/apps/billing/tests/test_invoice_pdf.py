"""Invoice PDF rendering (no database: the invoice is built in memory)."""

from datetime import UTC, datetime

from apps.billing import invoice_pdf
from apps.billing.models import Invoice

ISSUED = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)


def make_invoice(**fields) -> Invoice:
    values = dict(
        number="UPC/26-27/000007",
        financial_year="2026-27",
        status=Invoice.Status.PAID,
        issued_at=ISSUED,
        period_start=ISSUED,
        period_end=datetime(2026, 11, 20, 9, 30, tzinfo=UTC),
        description="UpChatz Growth plan (monthly)",
        sac_code="998314",
        gst_rate_percent=0,
        subtotal_paise=249900,
        total_paise=249900,
        payment_id="pay_test123",
        payment_provider="razorpay",
        seller={
            "legal_name": "Ibtaura Tech",
            "address": "Chennai",
            "gstin": "",
            "state_code": "33",
        },
        buyer={
            "legal_name": "Asha Textiles",
            "address_line1": "12 <Main> Road",
            "city": "Madurai",
            "postal_code": "625001",
            "state_code": "33",
            "email": "asha@example.com",
        },
    )
    values.update(fields)
    return Invoice(**values)


def test_format_amount_uses_indian_grouping():
    assert invoice_pdf.format_amount(249900) == "INR 2,499.00"
    assert invoice_pdf.format_amount(10000050) == "INR 1,00,000.50"
    assert invoice_pdf.format_amount(0) == "INR 0.00"


def test_renders_a_pdf_without_gst():
    invoice = make_invoice()

    content = invoice_pdf.render(invoice)

    assert content.startswith(b"%PDF")
    assert not invoice_pdf.is_tax_invoice(invoice)
    assert invoice_pdf.filename(invoice) == "UPC-26-27-000007.pdf"


def test_renders_a_tax_invoice_with_cgst_and_sgst():
    invoice = make_invoice(
        gst_rate_percent=18,
        cgst_paise=22491,
        sgst_paise=22491,
        total_paise=294882,
        seller={"legal_name": "Ibtaura Tech", "gstin": "33ABCDE1234F1Z5", "state_code": "33"},
    )

    assert invoice_pdf.is_tax_invoice(invoice)
    assert invoice_pdf.render(invoice).startswith(b"%PDF")


def test_renders_with_empty_snapshots():
    invoice = make_invoice(seller={}, buyer={}, payment_id=None, payment_provider="")

    assert invoice_pdf.render(invoice).startswith(b"%PDF")
