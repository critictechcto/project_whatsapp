"""Orders receivers: payment link events, the address-form fallback, and the claimer for typed
addresses. Buyer replies (``chk``, ``ord``, ``nfm``) reach orders through the shop, which calls
``orders.services``; orders registers no ``MessageRecorded`` receiver of its own."""

from django.dispatch import receiver

from common import events
from common.commerce import register_message_claimer

from . import checkout

register_message_claimer(checkout.claim_awaited_text)


@receiver(events.payment_link_paid, dispatch_uid="orders.on_payment_link_paid")
def on_payment_link_paid(sender, event: events.PaymentLinkPaid, **kwargs) -> None:
    checkout.on_payment_link_paid(event)


@receiver(events.payment_link_expired, dispatch_uid="orders.on_payment_link_expired")
def on_payment_link_expired(sender, event: events.PaymentLinkExpired, **kwargs) -> None:
    checkout.on_payment_link_closed(event, expired=True)


@receiver(events.payment_link_cancelled, dispatch_uid="orders.on_payment_link_cancelled")
def on_payment_link_cancelled(sender, event: events.PaymentLinkCancelled, **kwargs) -> None:
    checkout.on_payment_link_closed(event, expired=False)


@receiver(events.message_delivery_updated, dispatch_uid="orders.on_message_delivery_updated")
def on_message_delivery_updated(sender, event: events.MessageDeliveryUpdated, **kwargs) -> None:
    checkout.on_address_message_failed(event)
