"""Shared setup for the commerce end-to-end tests (this module holds no tests).

Buyers and sellers act only through signed Meta webhooks posted to ``/webhooks/meta/``: buyers
message the store number (``PHONE_NUMBER_ID``), sellers message the UpChatz alerts number
(``PLATFORM_WA_PHONE_NUMBER_ID``). Celery is eager, and ``deliver_meta`` runs every on-commit
callback, so one delivery plays out the whole chain: inbox → shop → orders → payments → alerts →
Graph sends recorded by the fake client.

Scenario modules load the fixtures with ``pytest_plugins = ["tests.test_e2e_commerce_support"]``
and import the plain helpers.
"""

import itertools
import json
import re
import time
from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.catalog.factories import CollectionFactory, ProductFactory
from apps.inbox.models import Conversation, Message
from apps.orders.factories import StoreSettingsFactory
from apps.orders.models import Order
from apps.payments.factories import PaymentAccountFactory
from apps.payments.models import PaymentLink
from apps.payments.testing import fake_payments  # noqa: F401  (pytest fixture)
from apps.seller_alerts.factories import AlertRecipientFactory
from common import realtime

from .conftest import CUSTOMER_WA_ID, DISPLAY_PHONE_NUMBER, PHONE_NUMBER_ID, WABA_ID

SELLER_PHONE = "+919700000001"
REPLY_ID_RE = re.compile(r'"(upc:[^"]+)"')
ADDRESS_FORM = {
    "name": "Priya Sharma",
    "phone_number": "+919876543210",
    "in_pin_code": "110001",
    "house_number": "14",
    "address": "Janpath Road",
    "landmark_area": "Connaught Place",
    "city": "New Delhi",
    "state": "Delhi",
}

_wamids = itertools.count(1)


# --- Webhook payloads ---------------------------------------------------------------------------


def messages_envelope(
    *, phone_number_id: str, display_phone_number: str, wa_id: str, name: str, message: dict
) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA_ID,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": display_phone_number,
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


class WhatsAppUser:
    """Someone messaging a business number. Each action delivers one signed webhook and returns
    its payload, so a test can deliver it again."""

    def __init__(self, deliver, *, wa_id: str, name: str, phone_number_id: str, display: str):
        self.deliver = deliver
        self.wa_id, self.name = wa_id, name
        self.phone_number_id, self.display = phone_number_id, display

    def send(self, body: dict, *, wamid: str | None = None) -> dict:
        message = {
            "from": self.wa_id,
            "id": wamid or f"wamid.E2E.COMMERCE{next(_wamids):06d}",
            "timestamp": str(int(time.time())),
            **body,
        }
        payload = messages_envelope(
            phone_number_id=self.phone_number_id,
            display_phone_number=self.display,
            wa_id=self.wa_id,
            name=self.name,
            message=message,
        )
        self.deliver(payload)
        return payload

    def says(self, text: str) -> dict:
        return self.send({"type": "text", "text": {"body": text}})

    def taps(self, reply_id: str, title: str = "Option") -> dict:
        """A reply button on an interactive message."""
        return self.send(
            {
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": reply_id, "title": title},
                },
            }
        )

    def picks(self, reply_id: str, title: str = "Row") -> dict:
        """A list row."""
        return self.send(
            {
                "type": "interactive",
                "interactive": {
                    "type": "list_reply",
                    "list_reply": {"id": reply_id, "title": title},
                },
            }
        )

    def taps_template_button(self, payload: str, text: str) -> dict:
        """A quick-reply button on a template message."""
        return self.send({"type": "button", "button": {"payload": payload, "text": text}})

    def shares_address(self, values: dict | None = None) -> dict:
        response_json = json.dumps({"values": ADDRESS_FORM if values is None else values})
        return self.send(
            {
                "type": "interactive",
                "interactive": {
                    "type": "nfm_reply",
                    "nfm_reply": {
                        "name": "address_message",
                        "body": "Sent",
                        "response_json": response_json,
                    },
                },
            }
        )

    def sends_cart(self, items: list[dict], catalog_id: str = "1234567890") -> dict:
        return self.send(
            {
                "type": "order",
                "order": {"catalog_id": catalog_id, "text": "", "product_items": items},
            }
        )


# --- Outbound inspection ------------------------------------------------------------------------


def reply_ids(data) -> list[str]:
    return REPLY_ID_RE.findall(json.dumps(data))


def option_id(message: Message | dict, title: str) -> str:
    """The reply id of the button or list row titled ``title``."""
    payload = message.payload if isinstance(message, Message) else message
    action = (payload.get("interactive") or {}).get("action") or {}
    for button in action.get("buttons", []):
        if button["reply"]["title"] == title:
            return button["reply"]["id"]
    for section in action.get("sections", []):
        for row in section.get("rows", []):
            if row["title"] == title:
                return row["id"]
    raise AssertionError(f"No option titled {title!r} in {json.dumps(payload)[:500]}")


def body_text(message: Message | dict) -> str:
    payload = message.payload if isinstance(message, Message) else message
    if payload.get("type") == "interactive":
        return payload["interactive"].get("body", {}).get("text", "")
    if payload.get("type") == "text":
        return payload["text"]["body"]
    if isinstance(message, Message):
        return message.text
    return json.dumps(payload)


def buyer_messages(workspace) -> list[Message]:
    return list(
        Message.objects.filter(
            workspace=workspace,
            direction=Message.Direction.OUTBOUND,
            conversation__contact__wa_id=CUSTOMER_WA_ID,
        ).order_by("created_at", "pk")
    )


def last_buyer_message(workspace) -> Message:
    messages = buyer_messages(workspace)
    assert messages, "the buyer got no message"
    return messages[-1]


def platform_sends(fake_graph, wa_id: str | None = None) -> list[dict]:
    """Messages sent from the UpChatz alerts number (optionally to one phone)."""
    return [
        sent
        for sent in fake_graph.sent_messages
        if sent["phone_number_id"] == settings.PLATFORM_WA_PHONE_NUMBER_ID
        and (wa_id is None or sent["to"] == wa_id)
    ]


def store_sends(fake_graph) -> list[dict]:
    return [sent for sent in fake_graph.sent_messages if sent["phone_number_id"] == PHONE_NUMBER_ID]


def close_buyer_window(workspace) -> None:
    Conversation.objects.filter(workspace=workspace, contact__wa_id=CUSTOMER_WA_ID).update(
        service_window_expires_at=timezone.now() - timedelta(minutes=1)
    )


def current_order(workspace) -> Order:
    return Order.objects.filter(workspace=workspace).latest("created_at")


def only_link(order: Order) -> PaymentLink:
    [link] = PaymentLink.objects.filter(order=order)
    return link


# --- Fixtures -----------------------------------------------------------------------------------


@pytest.fixture
def on_commit(django_capture_on_commit_callbacks):
    """``with on_commit():`` runs the callbacks queued in the block (tasks, events, frames)."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


@pytest.fixture
def frames(monkeypatch):
    """Realtime frames sent during the test."""
    sent: list[dict] = []
    monkeypatch.setattr(realtime, "_send", lambda group, frame: sent.append(frame))
    return sent


@pytest.fixture
def store(workspace, e2e_number):
    return StoreSettingsFactory(
        workspace=workspace,
        enabled=True,
        store_name="Sharma Sweets",
        order_prefix="SS",
        welcome_message="Namaste! Welcome to Sharma Sweets.",
    )


@pytest.fixture
def sweets(workspace):
    return CollectionFactory(workspace=workspace, name="Sweets", description="Fresh every day")


@pytest.fixture
def kaju(workspace, sweets):
    return ProductFactory(
        workspace=workspace,
        collection=sweets,
        sku="KAJU-250",
        name="Kaju Katli 250 g",
        price_paise=24900,
        stock_qty=10,
    )


@pytest.fixture
def gateway(workspace):
    """The seller's verified gateway account (the fake provider answers for it)."""
    return PaymentAccountFactory(workspace=workspace)


@pytest.fixture
def recipient(workspace, store):
    return AlertRecipientFactory(workspace=workspace, name="Ravi", phone_e164=SELLER_PHONE)


@pytest.fixture
def buyer(deliver_meta, store, fake_graph, fake_payments):  # noqa: F811
    return WhatsAppUser(
        deliver_meta,
        wa_id=CUSTOMER_WA_ID,
        name="Priya Sharma",
        phone_number_id=PHONE_NUMBER_ID,
        display=DISPLAY_PHONE_NUMBER,
    )


@pytest.fixture
def seller(deliver_meta):
    return WhatsAppUser(
        deliver_meta,
        wa_id=SELLER_PHONE.removeprefix("+"),
        name="Ravi",
        phone_number_id=settings.PLATFORM_WA_PHONE_NUMBER_ID,
        display=settings.PLATFORM_WA_DISPLAY_PHONE_NUMBER,
    )


# --- Journeys -----------------------------------------------------------------------------------


def shop_to_checkout(buyer: WhatsAppUser, workspace, *, quantity_taps: int = 1) -> Order:
    """ "hi" → Shop now → Sweets → Kaju Katli → Add to cart (``quantity_taps`` times) → Checkout.

    Returns the new order, waiting for the address."""
    tap_checkout(buyer, workspace, quantity_taps=quantity_taps)
    return current_order(workspace)


def tap_checkout(buyer: WhatsAppUser, workspace, *, quantity_taps: int = 1) -> None:
    """The shop steps of :func:`shop_to_checkout`, without expecting an order."""
    buyer.says("hi")
    buyer.taps(option_id(last_buyer_message(workspace), "Shop now"), "Shop now")
    buyer.picks(option_id(last_buyer_message(workspace), "Sweets"), "Sweets")
    buyer.picks(option_id(last_buyer_message(workspace), "Kaju Katli 250 g"), "Kaju Katli 250 g")
    card = last_buyer_message(workspace)
    for _ in range(quantity_taps):
        buyer.taps(option_id(card, "Add to cart"), "Add to cart")
    buyer.taps(option_id(last_buyer_message(workspace), "Checkout"), "Checkout")


def checkout_to_payment_choice(buyer: WhatsAppUser, workspace, **kwargs) -> Order:
    shop_to_checkout(buyer, workspace, **kwargs)
    buyer.shares_address()
    return current_order(workspace)


def pay_online(buyer: WhatsAppUser, workspace, **kwargs) -> Order:
    """Through checkout to a created payment link (the order is ``pending_payment``)."""
    checkout_to_payment_choice(buyer, workspace, **kwargs)
    buyer.taps(option_id(last_buyer_message(workspace), "Pay online"), "Pay online")
    return current_order(workspace)
