"""Seller alerts services: alert recipients, verification, order alerts and delivery from the
UpChatz alerts number (docs/contracts/wave-3-commerce.md, "Seller alerts")."""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.orders import services as order_services
from apps.orders.models import Order, OrderEvent
from apps.tenants.models import Workspace
from apps.whatsapp.client.errors import (
    GraphAPIError,
    OutsideWindowError,
    RecipientUnavailableError,
)
from common import realtime
from common.events import OrderStatusChanged
from common.exceptions import UpstreamUnavailable
from common.phone import InvalidPhoneNumber, normalize_e164, to_wa_id

from . import content
from .content import Outbound
from .exceptions import AlertRecipientLimit, PlatformAlertsUnavailable, VerificationRecentlySent
from .models import (
    MAX_RECIPIENTS_PER_WORKSPACE,
    AlertMessage,
    AlertRecipient,
    default_alert_events,
)
from .platform import (
    platform_alerts_available,
    platform_client,
    platform_phone_number_id,
    window_open,
)

logger = logging.getLogger(__name__)

VERIFICATION_COOLDOWN = timedelta(minutes=5)
ERROR_MESSAGE_MAX_LENGTH = 1000
RECIPIENT_UPDATED_FRAME = "alert_recipient.updated"

NEW_ORDER = "new_order"
NEEDS_ATTENTION = "needs_attention"
ORDER_CANCELLED = "order_cancelled"
# Cancellations the seller made themselves (dashboard or WhatsApp) don't alert, and neither do
# checkouts the seller never got a new-order alert for (superseded carts, Edit cart, buyer cancel).
CANCELLED_ALERT_ACTORS = frozenset({"buyer", "system"})


def ensure_platform_available() -> None:
    if not platform_alerts_available():
        raise PlatformAlertsUnavailable()


def store_name(workspace) -> str:
    name = order_services.get_store_settings(workspace).store_name or workspace.name or ""
    return name.strip() or "Your store"


# --- Delivery -----------------------------------------------------------------------------------


@dataclass
class Delivery:
    message: AlertMessage
    error: GraphAPIError | None = None


def deliver(
    recipient: AlertRecipient,
    outbound: Outbound,
    *,
    order: Order | None = None,
    message: AlertMessage | None = None,
    final: bool = True,
) -> Delivery:
    """Send ``outbound`` to ``recipient`` from the platform number and log it in ``message``.

    Free-form while the recipient's 24-hour window is open (or when there is no template);
    otherwise the platform template. A free-form send refused as outside the window falls back
    to the template once. A retryable failure leaves ``message`` queued unless ``final``.
    """
    now = timezone.now()
    if message is None:
        message = AlertMessage.objects.create(
            recipient=recipient,
            workspace_id=recipient.workspace_id,
            order=order,
            kind=outbound.kind,
            to_wa_id=recipient.wa_id,
        )
    use_template = outbound.template is not None and not window_open(recipient.last_inbound_at, now)
    fallback = False
    client = platform_client()
    try:
        request, response = _send(client, recipient.wa_id, outbound, use_template=use_template)
    except OutsideWindowError as exc:
        if use_template or outbound.template is None:
            return _record_failure(message, exc, final=final)
        logger.info("Platform %s message outside the window; sending the template", message.kind)
        fallback = use_template = True
        try:
            request, response = _send(client, recipient.wa_id, outbound, use_template=True)
        except GraphAPIError as template_exc:
            return _record_failure(message, template_exc, final=final)
    except GraphAPIError as exc:
        return _record_failure(message, exc, final=final)

    messages = response.get("messages") if isinstance(response, Mapping) else None
    first = messages[0] if isinstance(messages, list) and messages else None
    wamid = first.get("id") if isinstance(first, Mapping) else None
    message.wamid = str(wamid) if wamid else None
    message.status = AlertMessage.Status.SENT
    message.sent_at = now
    message.error_code = ""
    message.error_message = ""
    message.payload = {
        "mode": "template" if use_template else "free_form",
        "fallback": fallback,
        "request": request,
    }
    message.save(
        update_fields=[
            "wamid",
            "status",
            "sent_at",
            "error_code",
            "error_message",
            "payload",
            "updated_at",
        ]
    )
    AlertRecipient.objects.filter(pk=recipient.pk).update(last_sent_at=now)
    recipient.last_sent_at = now
    return Delivery(message)


def _send(client, wa_id: str, outbound: Outbound, *, use_template: bool):
    body = outbound.template_message() if use_template else outbound.free_form_message()
    request = {"to": wa_id, **body}
    return request, client.send_message(platform_phone_number_id(), request)


def _record_failure(message: AlertMessage, exc: GraphAPIError, *, final: bool) -> Delivery:
    message.error_code = str(exc.code if exc.code is not None else type(exc).__name__)[:64]
    message.error_message = str(exc.message or exc)[:ERROR_MESSAGE_MAX_LENGTH]
    fields = ["error_code", "error_message", "updated_at"]
    if final or not exc.retryable:
        message.status = AlertMessage.Status.FAILED
        fields.append("status")
    message.save(update_fields=fields)
    logger.warning(
        "Platform %s message %s failed: %s", message.kind, message.pk, exc, exc_info=False
    )
    return Delivery(message, exc)


# --- Recipients ---------------------------------------------------------------------------------


def normalize_recipient_phone(raw) -> str:
    try:
        return normalize_e164(raw)
    except InvalidPhoneNumber as exc:
        raise ValidationError({"phone_e164": [str(exc)]}) from exc


def _broadcast_status(recipient: AlertRecipient) -> None:
    realtime.broadcast(
        recipient.workspace_id,
        RECIPIENT_UPDATED_FRAME,
        {"recipient_id": recipient.pk, "status": recipient.status},
    )


def _verification_error(exc: GraphAPIError) -> Exception:
    if isinstance(exc, RecipientUnavailableError):
        return ValidationError(
            {
                "phone_e164": [
                    "We couldn't send a WhatsApp message to this number. Check that it uses "
                    "WhatsApp."
                ]
            }
        )
    logger.error("The platform verification message could not be sent: %s", exc)
    return PlatformAlertsUnavailable()


def create_recipient(
    workspace, *, name: str, phone_e164: str, events: Iterable[str] | None = None
) -> AlertRecipient:
    """Add an alert number (at most 3 per workspace) and send it the verification template.

    A number Meta can't reach is rejected (400 on ``phone_e164``) and not kept; a temporary Meta
    failure keeps the pending recipient so the admin can resend the verification.
    """
    ensure_platform_available()
    phone = normalize_recipient_phone(phone_e164)
    with transaction.atomic():
        # Serialize concurrent creates for the workspace so the limit holds.
        list(Workspace.objects.select_for_update().filter(pk=workspace.pk).values_list("pk"))
        existing = AlertRecipient.objects.filter(workspace=workspace)
        if existing.count() >= MAX_RECIPIENTS_PER_WORKSPACE:
            raise AlertRecipientLimit()
        if existing.filter(phone_e164=phone).exists():
            raise ValidationError({"phone_e164": ["This number already gets order alerts."]})
        recipient = AlertRecipient.objects.create(
            workspace=workspace,
            name=name,
            phone_e164=phone,
            wa_id=to_wa_id(phone),
            events=list(events) if events is not None else default_alert_events(),
            verification_sent_at=timezone.now(),
        )
    delivery = send_verification(recipient)
    if delivery.error is not None and not delivery.error.retryable:
        recipient.delete()
        raise _verification_error(delivery.error)
    return recipient


def send_verification(recipient: AlertRecipient) -> Delivery:
    outbound = content.verification(recipient.pk, store_name(recipient.workspace))
    delivery = deliver(recipient, outbound)
    if delivery.error is not None:
        # Not throttled: nothing reached the phone.
        AlertRecipient.objects.filter(pk=recipient.pk).update(verification_sent_at=None)
        recipient.verification_sent_at = None
    return delivery


def resend_verification(recipient: AlertRecipient) -> AlertRecipient:
    """Send the verification again (409 ``verification_recently_sent`` within 5 minutes)."""
    ensure_platform_available()
    now = timezone.now()
    with transaction.atomic():
        recipient = (
            AlertRecipient.objects.select_for_update(of=("self",))
            .select_related("workspace")
            .get(pk=recipient.pk)
        )
        sent_at = recipient.verification_sent_at
        if sent_at is not None and now - sent_at < VERIFICATION_COOLDOWN:
            raise VerificationRecentlySent()
        recipient.verification_sent_at = now
        recipient.save(update_fields=["verification_sent_at", "updated_at"])
    delivery = send_verification(recipient)
    if delivery.error is not None:
        if delivery.error.retryable:
            raise UpstreamUnavailable()
        raise _verification_error(delivery.error)
    return recipient


def update_recipient(
    recipient: AlertRecipient, *, name: str | None = None, events: Iterable[str] | None = None
) -> AlertRecipient:
    fields = []
    if name is not None:
        recipient.name = name
        fields.append("name")
    if events is not None:
        recipient.events = list(events)
        fields.append("events")
    if fields:
        recipient.save(update_fields=[*fields, "updated_at"])
    return recipient


def delete_recipient(recipient: AlertRecipient) -> None:
    recipient.delete()


def mark_verified(recipient: AlertRecipient, *, now=None) -> bool:
    """Record the recipient's opt-in (the *Confirm* tap). False when already verified."""
    if recipient.status == AlertRecipient.Status.VERIFIED:
        return False
    recipient.status = AlertRecipient.Status.VERIFIED
    recipient.verified_at = now or timezone.now()
    recipient.opted_out_at = None
    recipient.save(update_fields=["status", "verified_at", "opted_out_at", "updated_at"])
    _broadcast_status(recipient)
    return True


def mark_opted_out(recipient: AlertRecipient, *, now=None) -> bool:
    """``STOP``. False when already opted out."""
    if recipient.status == AlertRecipient.Status.OPTED_OUT:
        return False
    recipient.status = AlertRecipient.Status.OPTED_OUT
    recipient.opted_out_at = now or timezone.now()
    recipient.save(update_fields=["status", "opted_out_at", "updated_at"])
    _broadcast_status(recipient)
    return True


# --- Order alerts -------------------------------------------------------------------------------


def alert_event_for(event: OrderStatusChanged) -> str | None:
    """The ``AlertEventEnum`` value an order status change alerts about, if any."""
    new, old = event.new_status, event.old_status
    if new == old:
        return None
    if new == Order.Status.CONFIRMED and (old == "" or old in Order.CHECKOUT_STATUSES):
        return NEW_ORDER
    if new == Order.Status.NEEDS_ATTENTION:
        return NEEDS_ATTENTION
    if (
        new == Order.Status.CANCELLED
        and event.actor in CANCELLED_ALERT_ACTORS
        and old not in Order.CHECKOUT_STATUSES
    ):
        return ORDER_CANCELLED
    return None


def alert_dedupe_key(recipient_id, order_id, event: str, new_status: str) -> str:
    return f"{recipient_id}:{order_id}:{event}:{new_status}"


def attention_reason(order: Order) -> str:
    flagged = (
        OrderEvent.objects.filter(order=order, to_status=Order.Status.NEEDS_ATTENTION)
        .exclude(detail="")
        .order_by("-created_at")
        .first()
    )
    return flagged.detail if flagged else ""


def build_alert(order: Order, event: str, *, actor: str = "") -> Outbound:
    name = store_name(order.workspace)
    if event == NEW_ORDER:
        return content.new_order(order, name)
    if event == NEEDS_ATTENTION:
        return content.needs_attention(order, name, attention_reason(order))
    if event == ORDER_CANCELLED:
        return content.order_cancelled(order, name, actor)
    raise ValueError(f"Unknown alert event {event!r}.")
