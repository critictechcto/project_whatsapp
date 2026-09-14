"""Messages to the UpChatz alerts number: the verification tap and seller commands.

Handled once per ``wamid`` (webhook retries re-emit events). Commands are accepted only from a
phone that is a ``verified`` recipient, except the *Confirm* button; everything else from
unknown or unverified senders is logged and ignored. Every order action re-checks that the order
belongs to one of that phone's verified workspaces. Replies are sent after the transaction.
"""

import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.orders import services as order_services
from apps.orders.models import Order
from common.commerce import ReplyId, parse_reply_id
from common.events import PlatformInboundMessage

from . import content, services
from .content import AWB_EXAMPLE, Outbound, status_label
from .models import AlertInboundMessage, AlertRecipient, PendingSellerReply

logger = logging.getLogger(__name__)

SELLER_ACTOR = "seller_whatsapp"
SELLER_CANCEL_REASON = "Cancelled by the seller on WhatsApp"
AWB_REPLY_TTL = timedelta(minutes=30)
OPEN_ORDERS_LIMIT = 10
LOG_TEXT_MAX_LENGTH = 1000
LOG_REPLY_ID_MAX_LENGTH = 256
AWB_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{2,63}$")
COURIER_MAX_LENGTH = 100
TRACKING_URL_MAX_LENGTH = 500
_validate_https_url = URLValidator(schemes=["https"])

RecipientStatus = AlertRecipient.Status
ORDER_ACTIONS = ("pack", "ship", "cancel")
DONE_TEXT = {"packed": "marked as packed", "shipped": "marked as shipped", "cancelled": "cancelled"}


# --- Courier and AWB replies --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Shipment:
    courier_name: str
    awb_number: str
    tracking_url: str = ""


class ShipmentParseError(ValueError):
    pass


def parse_shipment(text: str) -> Shipment:
    """``"Blue Dart 1234567890 https://…"`` -> courier, AWB and an optional https tracking URL."""
    tokens = (text or "").replace(",", " ").split()
    tracking_url = ""
    if tokens and tokens[-1].lower().startswith(("http://", "https://", "www.")):
        candidate = tokens.pop()
        if not candidate.lower().startswith("https://"):
            raise ShipmentParseError("The tracking link must start with https://.")
        if len(candidate) > TRACKING_URL_MAX_LENGTH:
            raise ShipmentParseError("That tracking link is too long.")
        try:
            _validate_https_url(candidate)
        except DjangoValidationError:
            raise ShipmentParseError("That tracking link doesn't look right.") from None
        tracking_url = candidate
    if len(tokens) < 2:
        raise ShipmentParseError("Please send the courier name and the AWB number.")
    awb_number = tokens[-1]
    courier_name = " ".join(tokens[:-1])
    if not AWB_RE.fullmatch(awb_number):
        raise ShipmentParseError("The AWB number can only have letters, digits and dashes.")
    if len(courier_name) > COURIER_MAX_LENGTH:
        raise ShipmentParseError("The courier name is too long.")
    return Shipment(courier_name, awb_number, tracking_url)


# --- Handling -----------------------------------------------------------------------------------


@dataclass
class _Reply:
    recipient: AlertRecipient
    outbound: Outbound
    pending: PendingSellerReply | None = None


@dataclass
class _Context:
    event: PlatformInboundMessage
    recipients: list[AlertRecipient]
    now: datetime
    replies: list[_Reply] = field(default_factory=list)

    @property
    def verified(self) -> list[AlertRecipient]:
        return [r for r in self.recipients if r.status == RecipientStatus.VERIFIED]

    def reply(
        self,
        recipient: AlertRecipient,
        outbound: Outbound,
        pending: PendingSellerReply | None = None,
    ) -> None:
        self.replies.append(_Reply(recipient, outbound, pending))


def _received_at(timestamp, now: datetime) -> datetime:
    if not isinstance(timestamp, datetime):
        return now
    if timezone.is_naive(timestamp):
        timestamp = timestamp.replace(tzinfo=UTC)
    return min(timestamp, now)


def _touch_window(from_wa_id: str, received_at: datetime) -> None:
    """Every message from the phone opens (or extends) its 24-hour window, in every workspace."""
    AlertRecipient.objects.filter(wa_id=from_wa_id).filter(
        Q(last_inbound_at__isnull=True) | Q(last_inbound_at__lt=received_at)
    ).update(last_inbound_at=received_at)


def handle_inbound(event: PlatformInboundMessage) -> None:
    from_wa_id = str(event.from_wa_id or "").strip()
    if not from_wa_id or not event.wamid:
        logger.warning("Ignoring a platform message without a sender or wamid")
        return
    now = timezone.now()
    received_at = _received_at(event.timestamp, now)
    _touch_window(from_wa_id, received_at)

    with transaction.atomic():
        try:
            with transaction.atomic():
                log = AlertInboundMessage.objects.create(
                    wamid=event.wamid,
                    from_wa_id=from_wa_id,
                    type=(event.type or "")[:32],
                    text=(event.text or "")[:LOG_TEXT_MAX_LENGTH],
                    reply_id=(event.reply_id or "")[:LOG_REPLY_ID_MAX_LENGTH],
                    received_at=received_at,
                )
        except IntegrityError:
            logger.info("Platform message %s was already handled", event.wamid)
            return
        recipients = list(
            AlertRecipient.objects.select_for_update(of=("self",))
            .select_related("workspace")
            .filter(wa_id=from_wa_id)
            .order_by("created_at")
        )
        context = _Context(event, recipients, now)
        if not _dispatch(context):
            log.outcome = AlertInboundMessage.Outcome.IGNORED
            log.save(update_fields=["outcome", "updated_at"])
            logger.info(
                "Ignored platform message %s from an unknown or unverified sender", event.wamid
            )

    for reply in context.replies:
        delivery = services.deliver(reply.recipient, reply.outbound)
        if reply.pending is not None and delivery.message.wamid:
            PendingSellerReply.objects.filter(pk=reply.pending.pk).update(
                prompt_wamid=delivery.message.wamid
            )


def _dispatch(ctx: _Context) -> bool:
    """Handle the message; False when it is ignored (unknown or unverified sender)."""
    reply = parse_reply_id(ctx.event.reply_id)
    if reply is not None and reply.scope == "alerts" and reply.action == "verify":
        return _verify(ctx, reply)
    command = (ctx.event.text or "").strip().upper() if reply is None else ""
    if command == "STOP":
        return _stop(ctx)
    verified = ctx.verified
    if not verified:
        return False
    if reply is not None:
        _handle_reply(ctx, verified, reply)
    elif command == "ORDERS":
        _send_open_orders(ctx, verified)
    elif command == "HELP" or not _handle_awaited_shipment(ctx, verified):
        ctx.reply(verified[0], content.help_message())
    return True


def _verify(ctx: _Context, reply: ReplyId) -> bool:
    target = reply.args[0] if len(reply.args) == 1 else None
    # Only the phone the verification was sent to can confirm it.
    recipient = next((r for r in ctx.recipients if str(r.pk) == target), None)
    if recipient is None:
        return False
    name = services.store_name(recipient.workspace)
    if services.mark_verified(recipient, now=ctx.now):
        ctx.reply(recipient, content.verified_confirmation(name))
    else:
        ctx.reply(
            recipient, content.help_message(f"This number already gets order alerts for {name}.")
        )
    return True


def _stop(ctx: _Context) -> bool:
    if not ctx.recipients:
        return False
    verified = ctx.verified
    changed = [r for r in ctx.recipients if services.mark_opted_out(r, now=ctx.now)]
    PendingSellerReply.objects.filter(recipient__in=ctx.recipients).delete()
    if verified:
        ctx.reply(verified[0], content.stopped())
    return bool(verified or changed)


def _find_order(
    verified: list[AlertRecipient], order_id: str
) -> tuple[Order | None, AlertRecipient | None]:
    """The order, locked, only when it belongs to one of the phone's verified workspaces."""
    try:
        order_uuid = uuid.UUID(order_id)
    except (TypeError, ValueError):
        return None, None
    by_workspace = {r.workspace_id: r for r in verified}
    order = (
        Order.objects.select_for_update(of=("self",))
        .select_related("workspace")
        .filter(pk=order_uuid, workspace_id__in=list(by_workspace))
        .first()
    )
    if order is None:
        return None, None
    return order, by_workspace[order.workspace_id]


def _handle_reply(ctx: _Context, verified: list[AlertRecipient], reply: ReplyId) -> None:
    if reply.scope == "alerts" and reply.action == "orders" and len(reply.args) <= 1:
        if reply.args:
            _send_order_details(ctx, verified, reply.args[0])
        else:
            _send_open_orders(ctx, verified)
        return
    if reply.scope == "alerts" and reply.action in ORDER_ACTIONS and len(reply.args) == 1:
        order, recipient = _find_order(verified, reply.args[0])
        if order is None:
            ctx.reply(verified[0], content.stale_option())
        elif reply.action == "pack":
            _pack(ctx, recipient, order)
        elif reply.action == "ship":
            _ask_for_shipment(ctx, recipient, order)
        else:
            _cancel(ctx, recipient, order)
        return
    ctx.reply(verified[0], content.stale_option())


def _run(action: Callable[[], object]) -> APIException | None:
    """Run an orders service call in a savepoint; its API error, if any."""
    try:
        with transaction.atomic():
            action()
    except APIException as exc:
        return exc
    return None


def _first_message(exc: APIException) -> str:
    detail = exc.detail
    while isinstance(detail, dict | list) and detail:
        detail = next(iter(detail.values())) if isinstance(detail, dict) else detail[0]
    return str(detail) if detail else "Please update it in UpChatz."


def _failure_text(order: Order, to_status: str, exc: APIException) -> str:
    if getattr(exc, "default_code", None) == "invalid_order_transition":
        current = Order.objects.filter(pk=order.pk).values_list("status", flat=True).first()
        return (
            f"Order {order.number} can't be {DONE_TEXT[to_status]} because it is "
            f"{status_label(current or order.status).lower()}."
        )
    return f"Couldn't update order {order.number}. {_first_message(exc)}"


def _pack(ctx: _Context, recipient: AlertRecipient, order: Order) -> None:
    error = _run(lambda: order_services.transition(order, "packed", actor=SELLER_ACTOR))
    if error is None:
        ctx.reply(recipient, content.text(f"Order {order.number} is marked as packed."))
    else:
        ctx.reply(recipient, content.text(_failure_text(order, "packed", error)))


def _cancel(ctx: _Context, recipient: AlertRecipient, order: Order) -> None:
    error = _run(
        lambda: order_services.cancel_order(order, actor=SELLER_ACTOR, reason=SELLER_CANCEL_REASON)
    )
    if error is None:
        ctx.reply(recipient, content.text(f"Order {order.number} is cancelled."))
    else:
        ctx.reply(recipient, content.text(_failure_text(order, "cancelled", error)))


def _ask_for_shipment(ctx: _Context, recipient: AlertRecipient, order: Order) -> None:
    if Order.Status.SHIPPED not in order.allowed_transitions:
        ctx.reply(
            recipient,
            content.text(
                f"Order {order.number} can't be marked as shipped because it is "
                f"{status_label(order.status).lower()}."
            ),
        )
        return
    # A bare courier reply always applies to the order that asked last.
    PendingSellerReply.objects.filter(recipient__in=ctx.recipients).delete()
    pending = PendingSellerReply.objects.create(
        workspace_id=order.workspace_id,
        recipient=recipient,
        order=order,
        action=PendingSellerReply.Action.AWAITING_AWB,
        expires_at=ctx.now + AWB_REPLY_TTL,
    )
    ctx.reply(recipient, content.awb_prompt(order), pending)


def _handle_awaited_shipment(ctx: _Context, verified: list[AlertRecipient]) -> bool:
    pending = (
        PendingSellerReply.objects.select_related("order")
        .filter(recipient__in=verified, action=PendingSellerReply.Action.AWAITING_AWB)
        .order_by("-created_at")
        .first()
    )
    if pending is None:
        return False
    recipient = next(r for r in verified if r.pk == pending.recipient_id)
    if pending.expires_at <= ctx.now:
        PendingSellerReply.objects.filter(recipient__in=ctx.recipients).delete()
        ctx.reply(
            recipient,
            content.help_message(
                f"The request for courier details for order {pending.order.number} has expired. "
                "Open the order and tap Mark shipped to try again."
            ),
        )
        return True
    try:
        shipment = parse_shipment(ctx.event.text or "")
    except ShipmentParseError as exc:
        ctx.reply(recipient, content.text(f"{exc} Send it like this:\n{AWB_EXAMPLE}"))
        return True
    order, recipient = _find_order(verified, str(pending.order_id))
    if order is None:
        pending.delete()
        ctx.reply(verified[0], content.stale_option())
        return True
    error = _run(
        lambda: order_services.transition(
            order,
            "shipped",
            actor=SELLER_ACTOR,
            courier_name=shipment.courier_name,
            awb_number=shipment.awb_number,
            tracking_url=shipment.tracking_url,
        )
    )
    if isinstance(error, ValidationError):
        # Keep waiting: the seller can send corrected details.
        ctx.reply(
            recipient,
            content.text(
                f"Couldn't mark order {order.number} as shipped: {_first_message(error)} "
                "Send the courier and AWB again."
            ),
        )
        return True
    pending.delete()
    if error is None:
        ctx.reply(
            recipient,
            content.text(
                f"Order {order.number} is marked as shipped with {shipment.courier_name} "
                f"(AWB {shipment.awb_number})."
            ),
        )
    else:
        ctx.reply(recipient, content.text(_failure_text(order, "shipped", error)))
    return True


def _send_open_orders(ctx: _Context, verified: list[AlertRecipient]) -> None:
    workspace_ids = [r.workspace_id for r in verified]
    allowed = set(workspace_ids)
    orders = order_services.open_orders_for_workspaces(workspace_ids, limit=OPEN_ORDERS_LIMIT)
    orders = [order for order in orders if order.workspace_id in allowed][:OPEN_ORDERS_LIMIT]
    names = {r.workspace_id: services.store_name(r.workspace) for r in verified}
    ctx.reply(verified[0], content.order_list(orders, names))


def _send_order_details(ctx: _Context, verified: list[AlertRecipient], order_id: str) -> None:
    order, recipient = _find_order(verified, order_id)
    if order is None:
        ctx.reply(verified[0], content.stale_option())
        return
    ctx.reply(recipient, content.order_details(order, services.store_name(order.workspace)))
