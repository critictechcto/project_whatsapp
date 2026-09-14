"""React to Meta webhook events parsed by the webhooks app. Every receiver is idempotent."""

from collections.abc import Mapping
from typing import Any

from django.db import transaction
from django.dispatch import receiver
from django.utils import timezone

from common.events import (
    AccountUpdate,
    PhoneNumberQualityUpdate,
    account_updated,
    phone_number_quality_updated,
)

from .models import PhoneNumber, WhatsAppBusinessAccount
from .services import digits_only

Status = WhatsAppBusinessAccount.Status

DISCONNECT_EVENTS = frozenset({"PARTNER_REMOVED", "PARTNER_APP_UNINSTALLED", "ACCOUNT_DELETED"})
RESTRICT_EVENTS = frozenset({"ACCOUNT_VIOLATION", "ACCOUNT_RESTRICTION"})
NOTE_EVENTS = frozenset({"VERIFIED_ACCOUNT", "BUSINESS_VERIFICATION_STATUS_UPDATE"})


@receiver(phone_number_quality_updated)
def on_phone_number_quality_updated(sender, event: PhoneNumberQualityUpdate, **kwargs) -> None:
    from .tasks import refresh_phone_number

    digits = digits_only(event.display_phone_number)
    if not digits:
        return
    candidates = PhoneNumber.objects.filter(
        waba__waba_id=event.waba_id,
        waba__workspace_id=event.workspace_id,
        workspace_id=event.workspace_id,
    )
    phone = next((p for p in candidates if digits_only(p.display_phone_number) == digits), None)
    if phone is None:
        return
    if event.current_limit and phone.messaging_limit_tier != event.current_limit[:32]:
        PhoneNumber.objects.filter(pk=phone.pk).update(
            messaging_limit_tier=event.current_limit[:32], updated_at=timezone.now()
        )
    phone_pk = str(phone.pk)
    transaction.on_commit(lambda: refresh_phone_number.delay(phone_pk))


def _value(payload: Mapping[str, Any], key: str) -> Any:
    """Look for ``key`` in the change value, tolerating a wrapped ``{"value": ...}`` payload."""
    if key in payload:
        return payload[key]
    inner = payload.get("value")
    return inner.get(key) if isinstance(inner, Mapping) else None


def _account_status(waba: WhatsAppBusinessAccount, event: AccountUpdate) -> tuple[str, str] | None:
    """New ``(status, note)`` for an account update, or ``None`` to ignore it."""
    name = event.event.upper()
    completed = waba.onboarding_status == WhatsAppBusinessAccount.OnboardingStatus.COMPLETED
    recovered = Status.ACTIVE if completed else Status.PENDING
    if name in DISCONNECT_EVENTS:
        return Status.DISCONNECTED, f"Meta account update: {name}. Reconnect required"
    if name == "DISABLED_UPDATE":
        ban_info = _value(event.payload, "ban_info")
        ban_state = str(ban_info.get("waba_ban_state", "")) if isinstance(ban_info, Mapping) else ""
        if ban_state == "REINSTATE":
            return recovered, "Meta account update: DISABLED_UPDATE (REINSTATE)"
        if ban_state == "SCHEDULE_FOR_DISABLE":
            return Status.RESTRICTED, "Meta account update: DISABLED_UPDATE (SCHEDULE_FOR_DISABLE)"
        return Status.DISABLED, f"Meta account update: DISABLED_UPDATE ({ban_state or 'DISABLE'})"
    if name in RESTRICT_EVENTS:
        if name == "ACCOUNT_RESTRICTION" and _value(event.payload, "restriction_info") == []:
            return recovered, "Meta account update: ACCOUNT_RESTRICTION lifted"
        detail = _value(event.payload, "violation_info") or _value(
            event.payload, "restriction_info"
        )
        note = f"Meta account update: {name}"
        if isinstance(detail, Mapping) and detail.get("violation_type"):
            note = f"{note} ({detail['violation_type']})"
        return Status.RESTRICTED, note
    if name in NOTE_EVENTS:
        return waba.status, f"Meta account update: {name}"
    return None


@receiver(account_updated)
def on_account_updated(sender, event: AccountUpdate, **kwargs) -> None:
    waba = WhatsAppBusinessAccount.objects.filter(
        waba_id=event.waba_id, workspace_id=event.workspace_id
    ).first()
    if waba is None:
        return
    if waba.status == Status.DISCONNECTED:
        return  # Only a new Embedded Signup brings a disconnected account back.
    change = _account_status(waba, event)
    if change is None:
        return
    new_status, note = change
    fields = {"status": new_status, "last_error": note[:1000]}
    if new_status == Status.DISCONNECTED:
        fields.update(access_token="", token_expires_at=None, subscribed_at=None)
    if all(getattr(waba, name) == value for name, value in fields.items()):
        return
    for name, value in fields.items():
        setattr(waba, name, value)
    waba.save(update_fields=[*fields, "updated_at"])
    if new_status == Status.DISCONNECTED:
        waba.phone_numbers.filter(is_default=True).update(
            is_default=False, updated_at=timezone.now()
        )
