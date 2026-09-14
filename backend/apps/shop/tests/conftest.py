from dataclasses import dataclass, field

import pytest

from apps.catalog.factories import CollectionFactory, ProductFactory
from apps.contacts.factories import ContactFactory
from apps.contacts.models import Contact
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import Message
from apps.orders import services as orders_services
from apps.orders.factories import StoreSettingsFactory
from apps.shop import services
from apps.whatsapp.factories import PhoneNumberFactory


@pytest.fixture(autouse=True)
def _no_network(fake_graph):
    """Every test runs with the fake Graph client."""
    return fake_graph


@pytest.fixture
def number(workspace):
    """The workspace's default, registered number (the store number)."""
    return PhoneNumberFactory(workspace=workspace, waba__workspace=workspace, is_default=True)


@pytest.fixture
def contact(workspace):
    return ContactFactory(
        workspace=workspace,
        name="Asha Verma",
        marketing_opt_in_status=Contact.OptInStatus.OPTED_IN,
    )


@pytest.fixture
def conversation(contact, number):
    """Conversation on the store number with an open service window."""
    return ConversationFactory(
        workspace=contact.workspace, contact=contact, phone_number=number, window_open=True
    )


@pytest.fixture
def store(workspace, number):
    return StoreSettingsFactory(
        workspace=workspace,
        enabled=True,
        store_name="Sharma Sweets",
        welcome_message="Namaste! Welcome to Sharma Sweets.",
        support_message="Call us on 98000 00000 between 10 and 7.",
    )


@pytest.fixture
def sweets(workspace):
    return CollectionFactory(workspace=workspace, name="Sweets", description="Fresh every day")


@pytest.fixture
def product(workspace, sweets):
    return ProductFactory(
        workspace=workspace,
        collection=sweets,
        name="Kaju Katli 500g",
        price_paise=59900,
        sale_price_paise=49900,
    )


@dataclass
class OrdersCalls:
    start_checkout: list = field(default_factory=list)
    replies: list = field(default_factory=list)
    texts: list = field(default_factory=list)
    recent_orders: list = field(default_factory=list)
    reply_result: bool = True
    text_result: bool = False


@pytest.fixture
def orders_calls(monkeypatch):
    """Record calls to the orders checkout services (implemented by another app)."""
    calls = OrdersCalls()

    def start_checkout(**kwargs):
        calls.start_checkout.append(kwargs)

    def handle_checkout_reply(message, reply):
        calls.replies.append((message, reply))
        return calls.reply_result

    def handle_checkout_text(message):
        calls.texts.append(message)
        return calls.text_result

    def send_recent_orders(conversation):
        calls.recent_orders.append(conversation)

    monkeypatch.setattr(orders_services, "start_checkout", start_checkout)
    monkeypatch.setattr(orders_services, "handle_checkout_reply", handle_checkout_reply)
    monkeypatch.setattr(orders_services, "handle_checkout_text", handle_checkout_text)
    monkeypatch.setattr(orders_services, "send_recent_orders", send_recent_orders)
    return calls


@pytest.fixture
def buyer(conversation, orders_calls):
    """``buyer.says("hi")`` / ``buyer.taps(reply_id)`` / ``buyer.sends_order(items)`` store an
    inbound message and run the bot on it; ``buyer.replies()`` lists the bot's messages."""

    class Buyer:
        def __init__(self) -> None:
            self.last = None
            self.seen = 0

        def _run(self, message, reply_id=None) -> bool:
            self.last = message
            return services.handle_inbound(message.pk, reply_id=reply_id)

        def says(self, text: str) -> bool:
            return self._run(MessageFactory(conversation=conversation, inbound=True, text=text))

        def taps(self, reply_id: str, title: str = "Option") -> bool:
            message = MessageFactory(
                conversation=conversation,
                inbound=True,
                type=Message.Type.INTERACTIVE,
                text=title,
                payload={
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {"id": reply_id, "title": title},
                    },
                },
            )
            return self._run(message, reply_id=reply_id)

        def sends_order(self, items: list[dict]) -> bool:
            message = MessageFactory(
                conversation=conversation,
                inbound=True,
                type=Message.Type.ORDER,
                text="Cart",
                payload={"type": "order", "order": {"catalog_id": "1", "product_items": items}},
            )
            return self._run(message)

        def replies(self) -> list[Message]:
            return list(
                Message.objects.filter(
                    conversation=conversation, direction=Message.Direction.OUTBOUND
                ).order_by("created_at", "pk")
            )

        def new_replies(self) -> list[Message]:
            replies = self.replies()
            fresh, self.seen = replies[self.seen :], len(replies)
            return fresh

        def last_reply(self) -> Message:
            return self.replies()[-1]

    return Buyer()
