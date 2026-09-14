"""The order status machine (docs/contracts/wave-3-commerce.md, "Transitions").

Manual transitions (dashboard, seller WhatsApp and buyer cancels) follow ``TRANSITIONS``. The
system may additionally move a checkout forward, expire it, or flag it ``needs_attention``;
pass ``system=True`` for those. No model imports: models import these constants.
"""

from .exceptions import InvalidOrderTransition
from .schema_enums import ORDER_STATUSES

DRAFT = "draft"
AWAITING_CONFIRMATION = "awaiting_confirmation"
AWAITING_ADDRESS = "awaiting_address"
AWAITING_PAYMENT_METHOD = "awaiting_payment_method"
PENDING_PAYMENT = "pending_payment"
CONFIRMED = "confirmed"
PACKED = "packed"
SHIPPED = "shipped"
DELIVERED = "delivered"
CANCELLED = "cancelled"
EXPIRED = "expired"
NEEDS_ATTENTION = "needs_attention"

CHECKOUT_STATUSES: tuple[str, ...] = (
    DRAFT,
    AWAITING_CONFIRMATION,
    AWAITING_ADDRESS,
    AWAITING_PAYMENT_METHOD,
    PENDING_PAYMENT,
)
OPEN_STATUSES: tuple[str, ...] = (CONFIRMED, PACKED, SHIPPED, NEEDS_ATTENTION)
CLOSED_STATUSES: tuple[str, ...] = (DELIVERED, CANCELLED, EXPIRED)

STAGE_STATUSES: dict[str, tuple[str, ...]] = {
    "checkout": CHECKOUT_STATUSES,
    "open": OPEN_STATUSES,
    "closed": CLOSED_STATUSES,
}

TRANSITIONS: dict[str, frozenset[str]] = {
    **{status: frozenset({CANCELLED}) for status in CHECKOUT_STATUSES},
    CONFIRMED: frozenset({PACKED, SHIPPED, CANCELLED}),
    PACKED: frozenset({SHIPPED, CANCELLED}),
    SHIPPED: frozenset({DELIVERED}),
    NEEDS_ATTENTION: frozenset({CONFIRMED, CANCELLED}),
    DELIVERED: frozenset(),
    CANCELLED: frozenset(),
    EXPIRED: frozenset(),
}

# Extra moves only the system makes: checkout steps in either direction (a buyer may edit the
# address), confirmation after payment or a COD choice, expiry, and flagging for the seller.
SYSTEM_TRANSITIONS: dict[str, frozenset[str]] = {
    status: frozenset({*CHECKOUT_STATUSES, CONFIRMED, EXPIRED, NEEDS_ATTENTION} - {status, DRAFT})
    for status in CHECKOUT_STATUSES
}


def stage_of(status: str) -> str:
    for stage, statuses in STAGE_STATUSES.items():
        if status in statuses:
            return stage
    raise ValueError(f"Unknown order status {status!r}.")


def allowed_transitions(status: str, *, system: bool = False) -> list[str]:
    """Statuses ``status`` may move to, in ``OrderStatusEnum`` order."""
    allowed = set(TRANSITIONS.get(status, ()))
    if system:
        allowed |= SYSTEM_TRANSITIONS.get(status, frozenset())
    return [value for value in ORDER_STATUSES if value in allowed]


def can_transition(order_status: str, to_status: str, *, system: bool = False) -> bool:
    return to_status in allowed_transitions(order_status, system=system)


def check_transition(order_status: str, to_status: str, *, system: bool = False) -> None:
    """Raise :class:`InvalidOrderTransition` (409) unless the move is allowed."""
    if not can_transition(order_status, to_status, system=system):
        raise InvalidOrderTransition(
            order_status, to_status, allowed_transitions(order_status, system=system)
        )
