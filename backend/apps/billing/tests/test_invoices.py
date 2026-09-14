"""GST arithmetic, financial years and invoice number formatting (pure functions)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.billing import invoices

IST = ZoneInfo("Asia/Kolkata")


def test_same_state_buyer_pays_cgst_and_sgst():
    gst = invoices.compute_gst(
        249900, buyer_state_code="29", seller_state_code="29", rate_percent=18
    )

    assert (gst.cgst_paise, gst.sgst_paise, gst.igst_paise) == (22491, 22491, 0)
    assert gst.intra_state is True
    assert gst.total_paise == 294882


def test_other_state_buyer_pays_igst():
    gst = invoices.compute_gst(
        249900, buyer_state_code="27", seller_state_code="29", rate_percent=18
    )

    assert (gst.cgst_paise, gst.sgst_paise, gst.igst_paise) == (0, 0, 44982)
    assert gst.intra_state is False
    assert gst.total_paise == 294882


@pytest.mark.parametrize(
    ("subtotal", "intra_state", "expected"),
    [
        (50, True, (5, 5, 0, 60)),  # 4.5 paise each rounds half up
        (50, False, (0, 0, 9, 59)),
        (12345, True, (1111, 1111, 0, 14567)),  # 1111.05
        (12345, False, (0, 0, 2222, 14567)),  # 2222.1
        (5, True, (0, 0, 0, 5)),  # 0.45
        (5, False, (0, 0, 1, 6)),  # 0.9
        (17, True, (2, 2, 0, 21)),  # 1.53
        (17, False, (0, 0, 3, 20)),  # 3.06
        (0, False, (0, 0, 0, 0)),
    ],
)
def test_each_tax_component_is_rounded_to_the_nearest_paisa(subtotal, intra_state, expected):
    gst = invoices.compute_gst(
        subtotal,
        buyer_state_code="29" if intra_state else "07",
        seller_state_code="29",
        rate_percent=18,
    )

    assert (gst.cgst_paise, gst.sgst_paise, gst.igst_paise, gst.total_paise) == expected


def test_buyer_without_a_state_is_charged_as_intra_state():
    gst = invoices.compute_gst(100000, buyer_state_code="", seller_state_code="29", rate_percent=5)

    assert (gst.cgst_paise, gst.sgst_paise, gst.igst_paise) == (2500, 2500, 0)


def test_negative_subtotal_is_rejected():
    with pytest.raises(ValueError):
        invoices.compute_gst(-1, buyer_state_code="29", seller_state_code="29", rate_percent=18)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 3, 31, 23, 59, 59, tzinfo=IST), "2025-26"),
        (datetime(2026, 4, 1, 0, 0, tzinfo=IST), "2026-27"),
        (datetime(2026, 3, 31, 18, 30, tzinfo=UTC), "2026-27"),  # 00:00 IST on 1 April
        (datetime(2026, 3, 31, 18, 29, 59, tzinfo=UTC), "2025-26"),
        (datetime(2027, 1, 15, tzinfo=UTC), "2026-27"),
        (datetime(2099, 12, 31, tzinfo=IST), "2099-00"),
    ],
)
def test_financial_year_runs_april_to_march_in_india(moment, expected):
    assert invoices.financial_year(moment) == expected


def test_financial_year_needs_an_aware_datetime():
    with pytest.raises(ValueError):
        invoices.financial_year(datetime(2026, 4, 1))


@pytest.mark.parametrize(
    ("fiscal_year", "serial", "expected"),
    [
        ("2026-27", 1, "UPC/26-27/000001"),
        ("2026-27", 999999, "UPC/26-27/999999"),
        ("2099-00", 12, "UPC/99-00/000012"),
    ],
)
def test_invoice_numbers_fit_gst_length_rules(fiscal_year, serial, expected):
    number = invoices.format_invoice_number(fiscal_year, serial)

    assert number == expected
    assert len(number) <= invoices.MAX_INVOICE_NUMBER_LENGTH


@pytest.mark.parametrize("serial", [0, 1_000_000])
def test_invoice_serial_must_be_in_range(serial):
    with pytest.raises(ValueError):
        invoices.format_invoice_number("2026-27", serial)


@pytest.mark.parametrize(
    ("paise", "expected"),
    [
        (99900, "₹999"),
        (249900, "₹2,499"),
        (2499000, "₹24,990"),
        (10000000, "₹1,00,000"),
        (1234567890, "₹1,23,45,678.90"),
        (50, "₹0.50"),
    ],
)
def test_format_inr_uses_indian_grouping(paise, expected):
    assert invoices.format_inr(paise) == expected
