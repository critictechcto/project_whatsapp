"""Orders services (docs/contracts/wave-3-commerce.md, "Orders services").

This module is the contract surface other apps import; signatures are frozen by the contract.
The implementations live in:

- ``store``: store settings, the store number and link, order numbers;
- ``checkout``: the buyer checkout on WhatsApp, payment links and payment events, expiry;
- ``lifecycle``: status changes, stock and the merchant actions;
- ``notifications``: buyer status notifications (session message or template).
"""

from .checkout import (
    handle_checkout_reply,
    handle_checkout_text,
    send_recent_orders,
    start_checkout,
)
from .exceptions import CheckoutRejected
from .lifecycle import (
    cancel_order,
    mark_cod_collected,
    mark_refunded,
    open_orders_for_workspaces,
    transition,
    update_notes,
)
from .notifications import notify_buyer
from .store import (
    derive_order_prefix,
    get_store_settings,
    next_order_number,
    store_link,
    store_phone_number,
)

__all__ = [
    "CheckoutRejected",
    "cancel_order",
    "derive_order_prefix",
    "get_store_settings",
    "handle_checkout_reply",
    "handle_checkout_text",
    "mark_cod_collected",
    "mark_refunded",
    "next_order_number",
    "notify_buyer",
    "open_orders_for_workspaces",
    "send_recent_orders",
    "start_checkout",
    "store_link",
    "store_phone_number",
    "transition",
    "update_notes",
]
