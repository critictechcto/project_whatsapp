"""Cross-app domain events.

The webhooks app parses Meta payloads into these dataclasses and sends the matching signal with
:func:`emit`. Other apps react in their ``receivers.py``; they never import each other. Receivers
get ``(sender, event, **kwargs)``, must be idempotent (webhook deliveries can repeat) and should
push slow work to Celery.

Changing a dataclass here is a contract change: lead-owned, never done inside an app branch.
"""

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.dispatch import Signal

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MetaError:
    code: int
    title: str = ""
    message: str = ""
    details: str = ""


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """A message a customer sent to one of our connected numbers."""

    workspace_id: uuid.UUID
    waba_id: str
    phone_number_id: str
    wamid: str
    from_wa_id: str  # sender's WhatsApp id: E.164 digits without '+'
    timestamp: datetime
    # text, image, audio, video, document, sticker, location, contacts, interactive, button,
    # reaction, order, system, unsupported
    type: str
    text: str | None = None  # text body, caption, button text or interactive reply title
    reply_id: str | None = None  # quick-reply button payload or interactive reply id
    profile_name: str | None = None
    context_wamid: str | None = None  # message this one replies to
    payload: Mapping[str, Any] = field(default_factory=dict)  # raw Meta message object
    webhook_event_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class MessageStatus:
    """Delivery status of a message we sent."""

    workspace_id: uuid.UUID
    waba_id: str
    phone_number_id: str
    wamid: str
    recipient_wa_id: str
    status: str  # sent, delivered, read, failed (Meta may add more; handle unknown values)
    timestamp: datetime
    conversation_id: str | None = None
    pricing_category: str | None = None  # marketing, utility, authentication, service, ...
    pricing_model: str | None = None
    billable: bool | None = None
    errors: tuple[MetaError, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)
    webhook_event_id: uuid.UUID | None = None

    @property
    def error_codes(self) -> frozenset[int]:
        return frozenset(error.code for error in self.errors)


@dataclass(frozen=True, slots=True)
class TemplateStatusUpdate:
    workspace_id: uuid.UUID
    waba_id: str
    meta_template_id: str
    name: str
    language: str
    # APPROVED, REJECTED, PENDING, PAUSED, DISABLED, FLAGGED, REINSTATED, PENDING_DELETION, ...
    event: str
    reason: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    webhook_event_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class TemplateCategoryUpdate:
    workspace_id: uuid.UUID
    waba_id: str
    meta_template_id: str
    name: str
    language: str
    previous_category: str
    new_category: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    webhook_event_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class TemplateQualityUpdate:
    workspace_id: uuid.UUID
    waba_id: str
    meta_template_id: str
    name: str
    language: str
    previous_quality_score: str
    new_quality_score: str  # GREEN, YELLOW, RED, UNKNOWN
    payload: Mapping[str, Any] = field(default_factory=dict)
    webhook_event_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class PhoneNumberQualityUpdate:
    """Meta identifies the number by display number only; match on digits within the WABA."""

    workspace_id: uuid.UUID
    waba_id: str
    display_phone_number: str
    event: str  # FLAGGED, UNFLAGGED, DOWNGRADE, UPGRADE, ...
    current_limit: str | None = None  # e.g. TIER_1K
    old_limit: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    webhook_event_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class AccountUpdate:
    workspace_id: uuid.UUID
    waba_id: str
    event: str  # e.g. VERIFIED_ACCOUNT, DISABLED_UPDATE, ACCOUNT_VIOLATION, PARTNER_REMOVED
    payload: Mapping[str, Any] = field(default_factory=dict)
    webhook_event_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class MessageRecorded:
    """The inbox stored a message (inbound from a webhook, or outbound queued for sending).

    ``phone_number_id`` is the ``whatsapp.PhoneNumber`` primary key, not Meta's id. Emitted on
    commit. Automations react to ``direction == "inbound"``.
    """

    workspace_id: uuid.UUID
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    contact_id: uuid.UUID
    phone_number_id: uuid.UUID
    direction: str  # inbound, outbound
    source: str  # inbound, inbox, campaign, automation, api
    source_ref: str
    type: str  # MessageTypeEnum value
    text: str
    reply_id: str | None  # quick-reply payload or interactive reply id (inbound only)
    wamid: str | None
    is_first_inbound: bool  # first inbound message of the conversation
    contact_created: bool  # the contact was created by this inbound message
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MessageDeliveryUpdated:
    """An outbound message changed delivery status (sent, delivered, read, failed). Emitted on
    commit; campaigns match ``source == "campaign"`` and ``source_ref``."""

    workspace_id: uuid.UUID
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    source: str
    source_ref: str
    status: str  # MessageStatusEnum value
    error_code: str  # "" when none
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceCreated:
    """A workspace was created with ``owner_id`` as its first owner. Emitted on commit by
    ``apps.tenants.services``; billing starts the trial."""

    workspace_id: uuid.UUID
    owner_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class MembershipRoleChanged:
    """A member's role changed. Emitted on commit by ``apps.tenants.services``; the inbox
    revokes that user's open WebSockets."""

    workspace_id: uuid.UUID
    user_id: uuid.UUID
    old_role: str
    new_role: str


@dataclass(frozen=True, slots=True)
class MembershipRemoved:
    """A member was removed or left the workspace. Emitted on commit by
    ``apps.tenants.services``; the inbox revokes that user's open WebSockets."""

    workspace_id: uuid.UUID
    user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class PlatformInboundMessage:
    """A message sent to UpChatz's own alerts number (``PLATFORM_WA_PHONE_NUMBER_ID``).

    Not tied to a workspace: the webhooks app routes it here instead of resolving a workspace,
    and ``apps.seller_alerts`` matches ``from_wa_id`` to verified alert recipients. Fields mean
    the same as in :class:`InboundMessage`.
    """

    phone_number_id: str
    wamid: str
    from_wa_id: str
    timestamp: datetime
    type: str
    text: str | None = None
    reply_id: str | None = None
    profile_name: str | None = None
    context_wamid: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    webhook_event_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class PaymentLinkPaid:
    """A seller's payment link was paid in full. Emitted once, on commit, by ``apps.payments``
    when the link state fetched from the gateway is paid and the amount and currency match.
    The state is fetched when the buyer returns from the gateway, by polling, or after an
    optional seller webhook whose signature was verified. Receivers dedupe on
    ``payment_link_id`` (a link is paid at most once)."""

    workspace_id: uuid.UUID
    order_id: uuid.UUID
    payment_link_id: uuid.UUID  # payments.PaymentLink primary key
    provider: str  # razorpay | cashfree
    provider_link_id: str  # the gateway's link id (Razorpay plink_..., Cashfree link_id)
    provider_payment_id: str  # the gateway's payment id; may be "" when it couldn't be fetched
    amount_paise: int
    currency: str
    paid_at: datetime


@dataclass(frozen=True, slots=True)
class PaymentLinkExpired:
    """A payment link expired unpaid (seen on the gateway by the return page, polling or an
    optional webhook, or expired locally after the final poll keeps failing). Emitted on commit
    by ``apps.payments``; ``provider`` is razorpay or cashfree."""

    workspace_id: uuid.UUID
    order_id: uuid.UUID
    payment_link_id: uuid.UUID
    provider: str
    provider_link_id: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class PaymentLinkCancelled:
    """A payment link was cancelled, by UpChatz or on the gateway side (seen by the return
    page, polling or an optional webhook). Emitted on commit by ``apps.payments``; ``provider``
    is razorpay or cashfree."""

    workspace_id: uuid.UUID
    order_id: uuid.UUID
    payment_link_id: uuid.UUID
    provider: str
    provider_link_id: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class OrderStatusChanged:
    """An order changed status or payment status. Emitted on commit by ``apps.orders``; seller
    alerts react to it. ``old_status`` is "" when the order was just created.
    ``phone_number_id`` is the ``whatsapp.PhoneNumber`` primary key."""

    workspace_id: uuid.UUID
    order_id: uuid.UUID
    order_number: str
    contact_id: uuid.UUID
    phone_number_id: uuid.UUID
    old_status: str  # OrderStatusEnum value or ""
    new_status: str  # OrderStatusEnum value
    payment_status: str  # PaymentStatusEnum value
    payment_method: str  # PaymentMethodEnum value or ""
    total_paise: int
    actor: str  # OrderEventActorEnum value: buyer, dashboard, seller_whatsapp, system
    actor_user_id: uuid.UUID | None
    occurred_at: datetime


inbound_message_received = Signal()
message_status_updated = Signal()
template_status_updated = Signal()
template_category_updated = Signal()
template_quality_updated = Signal()
phone_number_quality_updated = Signal()
account_updated = Signal()
message_recorded = Signal()
message_delivery_updated = Signal()
workspace_created = Signal()
membership_role_changed = Signal()
membership_removed = Signal()
platform_inbound_message_received = Signal()
payment_link_paid = Signal()
payment_link_expired = Signal()
payment_link_cancelled = Signal()
order_status_changed = Signal()

# Event class -> the signal it is sent on.
EVENT_SIGNALS: dict[type, Signal] = {
    InboundMessage: inbound_message_received,
    MessageStatus: message_status_updated,
    TemplateStatusUpdate: template_status_updated,
    TemplateCategoryUpdate: template_category_updated,
    TemplateQualityUpdate: template_quality_updated,
    PhoneNumberQualityUpdate: phone_number_quality_updated,
    AccountUpdate: account_updated,
    MessageRecorded: message_recorded,
    MessageDeliveryUpdated: message_delivery_updated,
    WorkspaceCreated: workspace_created,
    MembershipRoleChanged: membership_role_changed,
    MembershipRemoved: membership_removed,
    PlatformInboundMessage: platform_inbound_message_received,
    PaymentLinkPaid: payment_link_paid,
    PaymentLinkExpired: payment_link_expired,
    PaymentLinkCancelled: payment_link_cancelled,
    OrderStatusChanged: order_status_changed,
}


def emit(signal: Signal, event: object) -> list[tuple[object, Exception]]:
    """Send ``event`` to every receiver, isolating failures.

    Returns ``(receiver, exception)`` for each receiver that raised, so the caller can mark the
    source webhook event failed and retry (receivers are idempotent).
    """
    failures = []
    for receiver, result in signal.send_robust(sender=type(event), event=event):
        if isinstance(result, Exception):
            logger.error(
                "Receiver %r failed for %s",
                receiver,
                type(event).__name__,
                exc_info=(type(result), result, result.__traceback__),
            )
            failures.append((receiver, result))
    return failures
