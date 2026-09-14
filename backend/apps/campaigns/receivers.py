"""React to inbox and Meta events. Every receiver is idempotent: webhook retries re-emit events."""

import logging
from collections.abc import Mapping
from typing import Any

from django.dispatch import receiver

from apps.whatsapp.models import PhoneNumber
from apps.whatsapp.services import digits_only
from common.events import (
    AccountUpdate,
    MessageDeliveryUpdated,
    MessageRecorded,
    PhoneNumberQualityUpdate,
    TemplateCategoryUpdate,
    TemplateStatusUpdate,
    account_updated,
    message_delivery_updated,
    message_recorded,
    phone_number_quality_updated,
    template_category_updated,
    template_status_updated,
)

from . import services
from .models import Campaign

logger = logging.getLogger(__name__)

ACTIVE = (Campaign.Status.SCHEDULED, Campaign.Status.RUNNING)

# Template events that leave the template sendable (FLAGGED is a quality warning only).
SENDABLE_TEMPLATE_EVENTS = frozenset({"APPROVED", "REINSTATED", "FLAGGED"})
PHONE_PAUSE_EVENTS = frozenset({"DOWNGRADE", "FLAGGED"})
ACCOUNT_PAUSE_EVENTS = frozenset(
    {
        "ACCOUNT_VIOLATION",
        "ACCOUNT_RESTRICTION",
        "DISABLED_UPDATE",
        "PARTNER_REMOVED",
        "PARTNER_APP_UNINSTALLED",
        "ACCOUNT_DELETED",
    }
)


@receiver(message_delivery_updated, dispatch_uid="campaigns.on_message_delivery_updated")
def on_message_delivery_updated(sender, event: MessageDeliveryUpdated, **kwargs) -> None:
    services.apply_delivery_update(event)


@receiver(message_recorded, dispatch_uid="campaigns.on_message_recorded")
def on_message_recorded(sender, event: MessageRecorded, **kwargs) -> None:
    services.record_reply(event)


def _campaigns_for_template(event) -> list:
    return list(
        Campaign.objects.filter(
            workspace_id=event.workspace_id,
            status__in=ACTIVE,
            template__meta_template_id=str(event.meta_template_id),
        ).values_list("pk", flat=True)
    )


@receiver(template_status_updated, dispatch_uid="campaigns.on_template_status_updated")
def on_template_status_updated(sender, event: TemplateStatusUpdate, **kwargs) -> None:
    name = str(event.event or "").upper()
    if not name or name in SENDABLE_TEMPLATE_EVENTS or not event.meta_template_id:
        return
    reason = (
        f"Meta changed template {event.name} ({event.language}) to {name}. "
        "Sending was paused; resume once the template is approved again."
    )
    services.pause_active(_campaigns_for_template(event), reason)


@receiver(template_category_updated, dispatch_uid="campaigns.on_template_category_updated")
def on_template_category_updated(sender, event: TemplateCategoryUpdate, **kwargs) -> None:
    new = str(event.new_category or "").upper()
    previous = str(event.previous_category or "").upper()
    if not new or new == previous or not event.meta_template_id:
        return
    reason = (
        f"Meta changed the category of template {event.name} ({event.language}) from "
        f"{previous or 'unknown'} to {new}. Check the audience and estimated cost, then resume."
    )
    services.pause_active(_campaigns_for_template(event), reason)


@receiver(phone_number_quality_updated, dispatch_uid="campaigns.on_phone_number_quality_updated")
def on_phone_number_quality_updated(sender, event: PhoneNumberQualityUpdate, **kwargs) -> None:
    name = str(event.event or "").upper()
    digits = digits_only(event.display_phone_number)
    if name not in PHONE_PAUSE_EVENTS or not digits:
        return
    numbers = PhoneNumber.objects.filter(
        workspace_id=event.workspace_id, waba__waba_id=event.waba_id
    ).only("pk", "display_phone_number")
    number_ids = [n.pk for n in numbers if digits_only(n.display_phone_number) == digits]
    if not number_ids:
        return
    campaign_ids = Campaign.objects.filter(
        workspace_id=event.workspace_id, status__in=ACTIVE, phone_number_id__in=number_ids
    ).values_list("pk", flat=True)
    reason = (
        f"Meta reported a quality {name.lower()} for {event.display_phone_number}. Sending was "
        "paused; review the number's quality rating and messaging limit before resuming."
    )
    services.pause_active(list(campaign_ids), reason)


def _value(payload: Mapping[str, Any], key: str) -> Any:
    if key in payload:
        return payload[key]
    inner = payload.get("value")
    return inner.get(key) if isinstance(inner, Mapping) else None


def _restricts(event: AccountUpdate) -> bool:
    name = str(event.event or "").upper()
    if name not in ACCOUNT_PAUSE_EVENTS:
        return False
    if name == "ACCOUNT_RESTRICTION" and _value(event.payload, "restriction_info") == []:
        return False  # restriction lifted
    if name == "DISABLED_UPDATE":
        ban_info = _value(event.payload, "ban_info")
        state = str(ban_info.get("waba_ban_state", "")) if isinstance(ban_info, Mapping) else ""
        return state != "REINSTATE"
    return True


@receiver(account_updated, dispatch_uid="campaigns.on_account_updated")
def on_account_updated(sender, event: AccountUpdate, **kwargs) -> None:
    if not _restricts(event):
        return
    campaign_ids = Campaign.objects.filter(
        workspace_id=event.workspace_id,
        status__in=ACTIVE,
        phone_number__waba__waba_id=event.waba_id,
    ).values_list("pk", flat=True)
    reason = (
        f"Meta reported {str(event.event).upper()} for your WhatsApp Business Account. Sending "
        "was paused; resolve it in WhatsApp Manager, then resume."
    )
    services.pause_active(list(campaign_ids), reason)
