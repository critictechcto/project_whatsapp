"""Orders services (docs/contracts/wave-3-commerce.md, "Orders services").

Signatures are frozen by the contract. ``get_store_settings`` and ``next_order_number`` are
implemented; the checkout, transition and notification functions are stubs that the B-phase
agents implement.
"""

import re
from collections.abc import Iterable

from django.db import transaction

from apps.catalog.services import PricedCart
from apps.inbox.models import Conversation, Message
from apps.whatsapp.models import PhoneNumber
from common.commerce import ReplyId

from .models import DEFAULT_ORDER_PREFIX, Order, OrderCounter, StoreSettings

STORE_NAME_MAX_LENGTH = 60
PREFIX_MIN_LENGTH = 2
PREFIX_MAX_LENGTH = 5
_WORD_RE = re.compile(r"[A-Za-z]+")


def derive_order_prefix(store_name: str) -> str:
    """Order number prefix from a store name: the initials of its first words ("Sharma Sweets"
    -> "SS"), or the first letters of a single word ("Chaicraft" -> "CHA"); 2-5 capital letters,
    "UPC" when the name has no usable letters."""
    words = _WORD_RE.findall(store_name or "")
    initials = "".join(word[0] for word in words[:PREFIX_MAX_LENGTH]).upper()
    if len(initials) >= PREFIX_MIN_LENGTH:
        return initials
    if words and len(words[0]) >= PREFIX_MIN_LENGTH:
        return words[0][:3].upper()
    return DEFAULT_ORDER_PREFIX


def get_store_settings(workspace) -> StoreSettings:
    """The workspace's store settings, created with defaults on first use."""
    existing = StoreSettings.objects.filter(workspace=workspace).first()
    if existing is not None:
        return existing
    store_name = (workspace.name or "").strip()[:STORE_NAME_MAX_LENGTH]
    store_settings, _ = StoreSettings.objects.get_or_create(
        workspace=workspace,
        defaults={"store_name": store_name, "order_prefix": derive_order_prefix(store_name)},
    )
    return store_settings


def store_phone_number(store_settings: StoreSettings) -> PhoneNumber | None:
    """The store number: the one chosen in settings, else the workspace default number."""
    if store_settings.phone_number_id:
        return store_settings.phone_number
    return PhoneNumber.objects.filter(
        workspace_id=store_settings.workspace_id, is_default=True
    ).first()


def store_link(store_settings: StoreSettings) -> str | None:
    """``https://wa.me/<digits>?text=Hi`` for the store number, or None without one."""
    number = store_phone_number(store_settings)
    if number is None:
        return None
    digits = re.sub(r"\D", "", number.phone_e164 or number.display_phone_number)
    return f"https://wa.me/{digits}?text=Hi" if digits else None


def next_order_number(workspace) -> str:
    """Allocate the next ``<order_prefix>-<n>`` (1001, 1002, ...).

    Locks the workspace's counter row until the surrounding transaction ends, so concurrent
    checkouts get distinct numbers and a rolled-back order leaves no gap.
    """
    prefix = get_store_settings(workspace).order_prefix
    with transaction.atomic():
        OrderCounter.objects.bulk_create([OrderCounter(workspace=workspace)], ignore_conflicts=True)
        counter = OrderCounter.objects.select_for_update().get(workspace=workspace)
        counter.last_value += 1
        counter.save(update_fields=["last_value", "updated_at"])
    return f"{prefix}-{counter.last_value}"


# --- Stubs (B phase) --------------------------------------------------------------------------


def start_checkout(
    *,
    workspace,
    conversation: Conversation,
    cart: PricedCart,
    source: str,
    source_wamid: str | None = None,
    quoted_total_paise: int | None = None,
) -> Order:
    """Create an order from a priced cart and send the buyer the next checkout step.

    Supersedes (cancels) the contact's active checkout on the same number, reserves stock and
    is idempotent on ``source_wamid``.
    """
    raise NotImplementedError


def handle_checkout_reply(message: Message, reply: ReplyId) -> bool:
    """Handle a ``chk``, ``ord`` or ``nfm`` reply. Returns True when the reply was handled."""
    raise NotImplementedError


def handle_checkout_text(message: Message) -> bool:
    """Handle a typed address while a checkout awaits one. Returns True when handled."""
    raise NotImplementedError


def send_recent_orders(conversation: Conversation) -> None:
    """Send the buyer a "My orders" list of their latest orders (at most 10)."""
    raise NotImplementedError


def transition(
    order: Order,
    to_status: str,
    *,
    actor: str,
    user=None,
    courier_name: str = "",
    awb_number: str = "",
    tracking_url: str = "",
    notify_buyer: bool = True,
) -> Order:
    """Move ``order`` to ``to_status`` (409 ``invalid_order_transition`` otherwise), write an
    ``OrderEvent``, emit ``OrderStatusChanged`` on commit and notify the buyer."""
    raise NotImplementedError


def cancel_order(
    order: Order,
    *,
    actor: str,
    user=None,
    reason: str = "",
    restock: bool = True,
    notify_buyer: bool = True,
) -> Order:
    """Cancel ``order``, release reserved stock when ``restock``, cancel an open payment link
    and notify the buyer."""
    raise NotImplementedError


def mark_cod_collected(order: Order, *, actor: str, user=None) -> Order:
    """Record cash collected for a COD order that is shipped or delivered."""
    raise NotImplementedError


def open_orders_for_workspaces(workspace_ids: Iterable, *, limit: int = 10) -> list[Order]:
    """Latest open orders across workspaces (for the seller ``ORDERS`` command)."""
    raise NotImplementedError
