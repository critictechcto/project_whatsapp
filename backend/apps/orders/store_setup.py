"""Store settings changes, the setup checklist and starter templates
(docs/contracts/wave-3-commerce.md, "Store")."""

import re
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.billing import entitlements
from apps.catalog.models import Product
from apps.catalog.services import connected_catalog
from apps.message_templates import services as template_services
from apps.message_templates.models import MessageTemplate
from apps.payments import services as payment_services
from apps.whatsapp.models import PhoneNumber

from .exceptions import CatalogNotConnected, CommerceNotEnabled
from .models import StoreSettings
from .store import get_store_settings, store_phone_number

SIMPLE_FIELDS = (
    "shop_mode",
    "store_name",
    "welcome_message",
    "order_prefix",
    "min_order_paise",
    "shipping_fee_paise",
    "free_shipping_above_paise",
    "cod_enabled",
    "cod_fee_paise",
    "cod_max_order_paise",
    "support_message",
    "powered_by_footer",
)
STRIPPED_FIELDS = ("store_name", "order_prefix")

# Body variables each notification fills (notifications.template_params).
TEMPLATE_PARAM_COUNTS = {
    "confirmed": 4,
    "packed": 2,
    "shipped": 5,
    "delivered": 2,
    "cancelled": 3,
    "payment_reminder": 4,
}
# Status updates the checklist expects templates for (payment reminders are optional).
CHECKLIST_NOTIFICATIONS = ("confirmed", "packed", "shipped", "delivered", "cancelled")
_VARIABLE_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")

STARTER_LANGUAGE = "en"


@dataclass(frozen=True, slots=True)
class StarterTemplate:
    notification: str
    name: str
    body: str
    examples: tuple[str, ...]


STARTER_TEMPLATES = (
    StarterTemplate(
        "confirmed",
        "upc_order_confirmed",
        "Hi {{1}}, thank you for your order {{2}}. Total: {{3}}. Payment: {{4}}. "
        "We will message you when it ships.",
        ("Asha", "SS-1001", "₹1,450.00", "Paid online"),
    ),
    StarterTemplate(
        "packed",
        "upc_order_packed",
        "Hi {{1}}, your order {{2}} is packed and will be shipped soon.",
        ("Asha", "SS-1001"),
    ),
    StarterTemplate(
        "shipped",
        "upc_order_shipped",
        "Hi {{1}}, your order {{2}} has shipped with {{3}}. AWB: {{4}}. Track it here: {{5}}. "
        "Thank you for shopping with us.",
        ("Asha", "SS-1001", "Delhivery", "1234567890", "https://www.delhivery.com/track"),
    ),
    StarterTemplate(
        "delivered",
        "upc_order_delivered",
        "Hi {{1}}, your order {{2}} has been delivered. Thank you for shopping with us.",
        ("Asha", "SS-1001"),
    ),
    StarterTemplate(
        "cancelled",
        "upc_order_cancelled",
        "Hi {{1}}, your order {{2}} has been cancelled. Reason: {{3}}. "
        "Reply to this message if you have any questions.",
        ("Asha", "SS-1001", "Out of stock"),
    ),
    StarterTemplate(
        "payment_reminder",
        "upc_payment_reminder",
        "Hi {{1}}, your order {{2}} for {{3}} is waiting for payment. Pay here: {{4}}. "
        "Please ignore this message if you have already paid.",
        ("Asha", "SS-1001", "₹1,450.00", "https://rzp.io/i/example"),
    ),
)


# --- Settings -----------------------------------------------------------------------------------


def update_store_settings(workspace, data: dict) -> StoreSettings:
    """Apply validated ``StoreSettingsSerializer`` data (partial)."""
    with transaction.atomic():
        store_settings = StoreSettings.objects.select_for_update().get(
            pk=get_store_settings(workspace).pk
        )
        was_enabled = store_settings.enabled
        changed: set[str] = set()
        for field in SIMPLE_FIELDS:
            if field in data:
                value = data[field]
                if field in STRIPPED_FIELDS:
                    value = (value or "").strip()
                setattr(store_settings, field, value)
                changed.add(field)
        if "menu_keywords" in data:
            store_settings.menu_keywords = _unique(
                keyword.strip().lower() for keyword in data["menu_keywords"]
            )
            changed.add("menu_keywords")
        if "serviceable_pincodes" in data:
            store_settings.serviceable_pincodes = _unique(data["serviceable_pincodes"])
            changed.add("serviceable_pincodes")
        if "phone_number_id" in data:
            store_settings.phone_number = _workspace_number(workspace, data["phone_number_id"])
            changed.add("phone_number")
        if "notification_templates" in data:
            changed |= _apply_templates(workspace, store_settings, data["notification_templates"])
        if "enabled" in data:
            store_settings.enabled = data["enabled"]
            changed.add("enabled")

        if store_settings.enabled and not was_enabled:
            _check_can_enable(workspace, store_settings)
        catalog_check = "shop_mode" in data or "phone_number_id" in data
        if (
            catalog_check
            and store_settings.shop_mode == StoreSettings.ShopMode.NATIVE_CATALOG
            and connected_catalog(workspace, store_phone_number(store_settings)) is None
        ):
            raise CatalogNotConnected()
        if changed:
            store_settings.save(update_fields=[*sorted(changed), "updated_at"])
    return store_settings


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _workspace_number(workspace, phone_number_id) -> PhoneNumber | None:
    if phone_number_id is None:
        return None
    number = (
        PhoneNumber.objects.select_related("waba")
        .filter(workspace=workspace, pk=phone_number_id)
        .first()
    )
    if number is None:
        raise ValidationError({"phone_number_id": ["Choose a WhatsApp number of this workspace."]})
    return number


def body_variable_count(template: MessageTemplate) -> int:
    for component in template.components or []:
        if isinstance(component, dict) and str(component.get("type", "")).upper() == "BODY":
            return len(set(_VARIABLE_RE.findall(str(component.get("text", "")))))
    return 0


def _apply_templates(workspace, store_settings: StoreSettings, mapping: dict) -> set[str]:
    number = store_phone_number(store_settings)
    changed, errors = set(), {}
    for notification, template_id in mapping.items():
        field = StoreSettings.NOTIFICATION_TEMPLATE_FIELDS[notification]
        if template_id is None:
            setattr(store_settings, field, None)
            changed.add(field)
            continue
        template = MessageTemplate.objects.filter(workspace=workspace, pk=template_id).first()
        if template is None:
            errors[notification] = ["Choose a message template of this workspace."]
            continue
        if number is not None and template.waba_id != number.waba_id:
            errors[notification] = [
                "Choose a template from the store number's WhatsApp Business Account."
            ]
            continue
        expected = TEMPLATE_PARAM_COUNTS[notification]
        if (found := body_variable_count(template)) != expected:
            errors[notification] = [
                f"This update fills {expected} body variables, but the template has {found}."
            ]
            continue
        setattr(store_settings, field, template)
        changed.add(field)
    if errors:
        raise ValidationError({"notification_templates": errors})
    return changed


def _check_can_enable(workspace, store_settings: StoreSettings) -> None:
    missing = []
    if not entitlements.has_feature(workspace, entitlements.COMMERCE):
        missing.append("a plan that includes selling on WhatsApp")
    if not Product.objects.filter(workspace=workspace, is_active=True).exists():
        missing.append("at least one active product")
    number = store_phone_number(store_settings)
    if number is None or not template_services.is_connected(number.waba):
        missing.append("a connected WhatsApp number")
    if missing:
        raise CommerceNotEnabled(f"To turn on the store, add {_join(missing)}.")


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# --- Checklist ----------------------------------------------------------------------------------


def _item(key: str, done: bool, detail: str) -> dict:
    return {"key": key, "done": bool(done), "detail": detail}


def _alert_recipient_verified(workspace) -> bool:
    """Read through the app registry: seller_alerts is not an allowed import for orders."""
    try:
        model = django_apps.get_model("seller_alerts", "AlertRecipient")
    except LookupError:
        return False
    return model.objects.filter(workspace=workspace, status="verified").exists()


def checklist(workspace) -> dict:
    store_settings = get_store_settings(workspace)
    items = []

    number = store_phone_number(store_settings)
    connected = number is not None and template_services.is_connected(number.waba)
    if connected:
        detail = f"Your store uses {number.display_phone_number}."
    elif number is not None:
        detail = f"Reconnect {number.display_phone_number} to sell on WhatsApp."
    else:
        detail = "Connect a WhatsApp number."
    items.append(_item("whatsapp_connected", connected, detail))

    products = Product.objects.filter(workspace=workspace, is_active=True).count()
    detail = (
        f"{products} active product{'s' if products != 1 else ''}."
        if products
        else "Add at least one active product."
    )
    items.append(_item("products_added", products > 0, detail))

    online = payment_services.online_payments_ready(workspace)
    cod = store_settings.cod_enabled
    if online and cod:
        detail = "Online payments and cash on delivery are on."
    elif online:
        detail = "Online payments are on."
    elif cod:
        detail = "Cash on delivery is on. Add your payment gateway keys to accept online payments."
    else:
        detail = "Add your payment gateway keys or turn on cash on delivery."
    items.append(_item("payments_configured", online or cod, detail))

    template_ids = [
        getattr(store_settings, f"{StoreSettings.NOTIFICATION_TEMPLATE_FIELDS[key]}_id")
        for key in CHECKLIST_NOTIFICATIONS
    ]
    approved = MessageTemplate.objects.filter(
        workspace=workspace,
        pk__in=[pk for pk in template_ids if pk],
        status=MessageTemplate.Status.APPROVED,
    ).count()
    total = len(CHECKLIST_NOTIFICATIONS)
    detail = (
        "Order update templates are approved."
        if approved == total
        else f"{approved} of {total} order update templates are mapped and approved."
    )
    items.append(_item("order_templates_ready", approved == total, detail))

    verified = _alert_recipient_verified(workspace)
    detail = (
        "Order alerts reach a verified number."
        if verified
        else "Verify a WhatsApp number for order alerts."
    )
    items.append(_item("alert_number_verified", verified, detail))

    detail = "Your store is live." if store_settings.enabled else "Turn on the store."
    items.append(_item("store_enabled", store_settings.enabled, detail))
    return {"items": items}


# --- Starter templates --------------------------------------------------------------------------


def starter_components(starter: StarterTemplate) -> list[dict]:
    return [
        {
            "type": "BODY",
            "text": starter.body,
            "example": {"body_text": [list(starter.examples)]},
        }
    ]


def create_starter_templates(workspace, *, user=None) -> dict:
    """Create the missing ``upc_*`` templates in the store number's WABA (UTILITY, ``en``), submit
    them for review and map them to notifications that have no template yet.

    A template left as a draft by an earlier failed attempt is submitted and counted as created.
    """
    store_settings = get_store_settings(workspace)
    number = store_phone_number(store_settings)
    if number is None or not template_services.is_connected(number.waba):
        raise template_services.WabaNotConnected(
            "Connect the store's WhatsApp number to create order templates."
        )
    waba = number.waba
    created, existing = [], []
    for starter in STARTER_TEMPLATES:
        template = MessageTemplate.objects.filter(
            waba=waba, name=starter.name, language=STARTER_LANGUAGE
        ).first()
        if template is None:
            template = template_services.create_draft(
                workspace=workspace,
                waba=waba,
                name=starter.name,
                language=STARTER_LANGUAGE,
                category=MessageTemplate.Category.UTILITY,
                components=starter_components(starter),
                created_by=user,
            )
        if template.status == MessageTemplate.Status.DRAFT:
            template = template_services.submit(template)
            created.append(starter.name)
        else:
            existing.append(starter.name)
        field = StoreSettings.NOTIFICATION_TEMPLATE_FIELDS[starter.notification]
        if getattr(store_settings, f"{field}_id") is None:
            setattr(store_settings, field, template)
            store_settings.save(update_fields=[field, "updated_at"])
    return {"created": created, "existing": existing}
