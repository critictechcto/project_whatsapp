"""Store settings helpers shared by checkout, notifications and the store API.

``services`` re-exports the public names; other modules in this app import from here so the
contract surface in ``services`` can import them without cycles.
"""

import re

from django.conf import settings
from django.db import transaction

from apps.message_templates import services as template_services
from apps.whatsapp.models import PhoneNumber

from .models import DEFAULT_ORDER_PREFIX, OrderCounter, StoreSettings

STORE_NAME_MAX_LENGTH = 60
PREFIX_MIN_LENGTH = 2
PREFIX_MAX_LENGTH = 5
POWERED_BY_FOOTER = "Powered by UpChatz"
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
    return (
        PhoneNumber.objects.select_related("waba")
        .filter(workspace_id=store_settings.workspace_id, is_default=True)
        .first()
    )


def store_number_connected(store_settings: StoreSettings) -> bool:
    number = store_phone_number(store_settings)
    return number is not None and template_services.is_connected(number.waba)


def store_link(store_settings: StoreSettings) -> str | None:
    """``https://wa.me/<digits>?text=Hi`` for the store number, or None without one."""
    number = store_phone_number(store_settings)
    if number is None:
        return None
    digits = re.sub(r"\D", "", number.phone_e164 or number.display_phone_number)
    return f"https://wa.me/{digits}?text=Hi" if digits else None


def store_display_name(store_settings: StoreSettings) -> str:
    return (store_settings.store_name or "").strip() or "our store"


def footer_for(store_settings: StoreSettings) -> str | None:
    return POWERED_BY_FOOTER if store_settings.powered_by_footer else None


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


def checkout_ttl_minutes() -> int:
    return int(settings.ORDER_CHECKOUT_TTL_MINUTES)


def payment_link_expiry_minutes() -> int:
    return int(settings.PAYMENT_LINK_EXPIRY_MINUTES)
