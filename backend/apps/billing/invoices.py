"""GST arithmetic and invoice numbering. Pure functions: no database, no settings.

Prices exclude GST; GST is added on top. A buyer in the seller's state pays CGST and SGST at half
the rate each; any other buyer pays IGST. Each tax component is rounded to the nearest paisa
(half up) and the total is the sum of the subtotal and the rounded components.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

INDIA_TZ = ZoneInfo("Asia/Kolkata")
INVOICE_PREFIX = "UPC"
INVOICE_SERIAL_DIGITS = 6
# GST rule 46(b): the invoice serial number may not exceed 16 characters.
MAX_INVOICE_NUMBER_LENGTH = 16


@dataclass(frozen=True, slots=True)
class GstBreakdown:
    subtotal_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    rate_percent: int
    intra_state: bool

    @property
    def tax_paise(self) -> int:
        return self.cgst_paise + self.sgst_paise + self.igst_paise

    @property
    def total_paise(self) -> int:
        return self.subtotal_paise + self.tax_paise


def _percent_of(amount_paise: int, percent: Decimal) -> int:
    value = Decimal(amount_paise) * percent / Decimal(100)
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def is_intra_state(buyer_state_code: str, seller_state_code: str) -> bool:
    """CGST + SGST applies when the buyer is in the seller's state.

    A buyer without a state on record is treated as intra-state: for services to an unregistered
    recipient without an address on record, the place of supply is the supplier's location.
    """
    return not buyer_state_code or buyer_state_code == seller_state_code


def compute_gst(
    subtotal_paise: int, *, buyer_state_code: str, seller_state_code: str, rate_percent: int
) -> GstBreakdown:
    if subtotal_paise < 0:
        raise ValueError("subtotal_paise must not be negative.")
    rate = Decimal(rate_percent)
    if is_intra_state(buyer_state_code, seller_state_code):
        half = _percent_of(subtotal_paise, rate / 2)
        return GstBreakdown(subtotal_paise, half, half, 0, rate_percent, intra_state=True)
    igst = _percent_of(subtotal_paise, rate)
    return GstBreakdown(subtotal_paise, 0, 0, igst, rate_percent, intra_state=False)


def financial_year(at: datetime) -> str:
    """Indian financial year (April-March, Asia/Kolkata) containing ``at``, e.g. ``2026-27``."""
    if at.tzinfo is None:
        raise ValueError("financial_year needs an aware datetime.")
    local = at.astimezone(INDIA_TZ)
    start = local.year if local.month >= 4 else local.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def format_invoice_number(fiscal_year: str, serial: int) -> str:
    """``UPC/26-27/000001`` for serial 1 of financial year ``2026-27`` (16 characters)."""
    if not 1 <= serial < 10**INVOICE_SERIAL_DIGITS:
        raise ValueError(f"Invoice serial {serial} is outside the series range.")
    start = int(fiscal_year[:4])
    short_year = f"{start % 100:02d}-{(start + 1) % 100:02d}"
    number = f"{INVOICE_PREFIX}/{short_year}/{serial:0{INVOICE_SERIAL_DIGITS}d}"
    if len(number) > MAX_INVOICE_NUMBER_LENGTH:  # pragma: no cover - guarded by the format
        raise ValueError("Invoice number is longer than GST rules allow.")
    return number


def format_inr(paise: int) -> str:
    """Indian digit grouping: 249900 → ``₹2,499``, 10000000 → ``₹1,00,000``."""
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
    return f"₹{digits}" + (f".{remainder:02d}" if remainder else "")
