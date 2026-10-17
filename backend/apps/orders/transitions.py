"""The order status machine (docs/contracts/wave-3-commerce.md, "Transitions", and
docs/contracts/services-and-offers.md for bookings).

An order is a ``delivery`` (products) or a ``booking`` (services); each kind has its own table.
Manual transitions (dashboard, seller WhatsApp and buyer cancels) follow ``TRANSITIONS``. The
system may additionally move a checkout forward, expire it, or flag it ``needs_attention``;
pass ``system=True`` for those. No model imports: models import these constants.
"""

from .exceptions import InvalidOrderTransition
from .schema_enums import ORDER_STATUSES

DELIVERY = "delivery"
BOOKING = "booking"
ORDER_KINDS = (DELIVERY, BOOKING)

DRAFT = "draft"
AWAITING_CONFIRMATION = "awaiting_confirmation"
AWAITING_ADDRESS = "awaiting_address"
AWAITING_TIME = "awaiting_time"
AWAITING_PAYMENT_METHOD = "awaiting_payment_method"
PENDING_PAYMENT = "pending_payment"
REQUESTED = "requested"
CONFIRMED = "confirmed"
PACKED = "packed"
SHIPPED = "shipped"
DELIVERED = "delivered"
COMPLETED = "completed"
NO_SHOW = "no_show"
CANCELLED = "cancelled"
EXPIRED = "expired"
NEEDS_ATTENTION = "needs_attention"

CHECKOUT_STATUSES: tuple[str, ...] = (
    DRAFT,
    AWAITING_CONFIRMATION,
    AWAITING_ADDRESS,
    AWAITING_TIME,
    AWAITING_PAYMENT_METHOD,
    PENDING_PAYMENT,
)
OPEN_STATUSES: tuple[str, ...] = (REQUESTED, CONFIRMED, PACKED, SHIPPED, NEEDS_ATTENTION)
CLOSED_STATUSES: tuple[str, ...] = (DELIVERED, COMPLETED, NO_SHOW, CANCELLED, EXPIRED)

STAGE_STATUSES: dict[str, tuple[str, ...]] = {
    "checkout": CHECKOUT_STATUSES,
    "open": OPEN_STATUSES,
    "closed": CLOSED_STATUSES,
}

# Checkout steps of each kind: a delivery asks for an address, a booking for a day and window.
KIND_CHECKOUT_STATUSES: dict[str, tuple[str, ...]] = {
    DELIVERY: tuple(status for status in CHECKOUT_STATUSES if status != AWAITING_TIME),
    BOOKING: tuple(status for status in CHECKOUT_STATUSES if status != AWAITING_ADDRESS),
}

TRANSITIONS: dict[str, dict[str, frozenset[str]]] = {
    DELIVERY: {
        **{status: frozenset({CANCELLED}) for status in KIND_CHECKOUT_STATUSES[DELIVERY]},
        CONFIRMED: frozenset({PACKED, SHIPPED, CANCELLED}),
        PACKED: frozenset({SHIPPED, CANCELLED}),
        SHIPPED: frozenset({DELIVERED}),
        NEEDS_ATTENTION: frozenset({CONFIRMED, CANCELLED}),
        DELIVERED: frozenset(),
        CANCELLED: frozenset(),
        EXPIRED: frozenset(),
    },
    BOOKING: {
        **{status: frozenset({CANCELLED}) for status in KIND_CHECKOUT_STATUSES[BOOKING]},
        REQUESTED: frozenset({CONFIRMED, CANCELLED}),
        CONFIRMED: frozenset({COMPLETED, NO_SHOW, CANCELLED}),
        NEEDS_ATTENTION: frozenset({REQUESTED, CANCELLED}),
        COMPLETED: frozenset(),
        NO_SHOW: frozenset(),
        CANCELLED: frozenset(),
        EXPIRED: frozenset(),
    },
}

# Where a finished checkout lands: deliveries are confirmed, bookings become requests that the
# seller confirms with a time.
CHECKOUT_DONE = {DELIVERY: CONFIRMED, BOOKING: REQUESTED}

# Extra moves only the system makes: checkout steps in either direction (a buyer may edit the
# address), the end of checkout after payment, a COD or pay-at-shop choice, expiry, and flagging
# for the seller.
SYSTEM_TRANSITIONS: dict[str, dict[str, frozenset[str]]] = {
    kind: {
        status: frozenset(
            {*statuses, CHECKOUT_DONE[kind], EXPIRED, NEEDS_ATTENTION} - {status, DRAFT}
        )
        for status in statuses
    }
    for kind, statuses in KIND_CHECKOUT_STATUSES.items()
}


def stage_of(status: str) -> str:
    for stage, statuses in STAGE_STATUSES.items():
        if status in statuses:
            return stage
    raise ValueError(f"Unknown order status {status!r}.")


def allowed_transitions(status: str, *, kind: str = DELIVERY, system: bool = False) -> list[str]:
    """Statuses ``status`` may move to, in ``OrderStatusEnum`` order."""
    kind = kind if kind in TRANSITIONS else DELIVERY
    allowed = set(TRANSITIONS[kind].get(status, ()))
    if system:
        allowed |= SYSTEM_TRANSITIONS[kind].get(status, frozenset())
    return [value for value in ORDER_STATUSES if value in allowed]


def can_transition(
    order_status: str, to_status: str, *, kind: str = DELIVERY, system: bool = False
) -> bool:
    return to_status in allowed_transitions(order_status, kind=kind, system=system)


def check_transition(
    order_status: str, to_status: str, *, kind: str = DELIVERY, system: bool = False
) -> None:
    """Raise :class:`InvalidOrderTransition` (409) unless the move is allowed."""
    if not can_transition(order_status, to_status, kind=kind, system=system):
        raise InvalidOrderTransition(
            order_status, to_status, allowed_transitions(order_status, kind=kind, system=system)
        )
