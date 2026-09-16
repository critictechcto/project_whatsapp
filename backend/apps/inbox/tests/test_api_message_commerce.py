"""Commerce fields on the message API: ``reply``, ``order_id`` and cart product names."""

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.factories import ProductFactory
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import Message
from apps.inbox.serializers import MessageSerializer
from common.commerce import build_reply_id
from common.roles import Role

pytestmark = pytest.mark.django_db


def messages_url(conversation) -> str:
    return f"/api/v1/inbox/conversations/{conversation.pk}/messages/"


def results_by_id(client, conversation) -> dict:
    response = client.get(messages_url(conversation))
    assert response.status_code == 200, response.content
    return {item["id"]: item for item in response.json()["results"]}


def interactive_reply(conversation, reply_type: str, reply: dict, text: str = "") -> Message:
    return MessageFactory(
        conversation=conversation,
        inbound=True,
        type=Message.Type.INTERACTIVE,
        text=text,
        payload={"type": "interactive", "interactive": {"type": reply_type, reply_type: reply}},
    )


def cart(conversation, *skus: str, **fields) -> Message:
    return MessageFactory(
        conversation=conversation,
        inbound=True,
        type=Message.Type.ORDER,
        text="Cart",
        payload={
            "type": "order",
            "order": {
                "catalog_id": "807010401234567",
                "product_items": [
                    {"product_retailer_id": sku, "quantity": 1, "item_price": 249} for sku in skus
                ],
            },
        },
        **fields,
    )


# --- reply --------------------------------------------------------------------------------------


def test_reply_kinds(auth_client, conversation):
    order_id = uuid.uuid4()
    button = interactive_reply(
        conversation,
        "button_reply",
        {"id": build_reply_id("chk", "confirm", order_id), "title": "Confirm order"},
        text="Confirm order",
    )
    row = interactive_reply(
        conversation,
        "list_reply",
        {"id": "upc:shop:col:all:0", "title": "Sweets", "description": "12 products"},
    )
    address = interactive_reply(
        conversation,
        "nfm_reply",
        {"name": "address_message", "response_json": "{}"},
        text="Address shared",
    )
    template_button = MessageFactory(
        conversation=conversation,
        inbound=True,
        type=Message.Type.BUTTON,
        text="Track order",
        payload={"type": "button", "button": {"text": "Track order", "payload": "track"}},
    )
    unknown = interactive_reply(conversation, "something_new", {"id": "x"})
    text = MessageFactory(conversation=conversation, inbound=True)
    outbound = MessageFactory(
        conversation=conversation,
        type=Message.Type.INTERACTIVE,
        payload={"interactive": {"type": "button_reply", "button_reply": {"id": "x"}}},
    )

    results = results_by_id(auth_client(Role.VIEWER), conversation)

    assert results[str(button.pk)]["reply"] == {
        "kind": "button",
        "id": f"upc:chk:confirm:{order_id}",
        "title": "Confirm order",
        "description": "",
    }
    assert results[str(button.pk)]["order_id"] == str(order_id)
    assert results[str(row.pk)]["reply"] == {
        "kind": "list",
        "id": "upc:shop:col:all:0",
        "title": "Sweets",
        "description": "12 products",
    }
    assert results[str(row.pk)]["order_id"] is None
    assert results[str(address.pk)]["reply"] == {
        "kind": "nfm",
        "id": "address_message",
        "title": "Address shared",
        "description": "",
    }
    assert results[str(template_button.pk)]["reply"] == {
        "kind": "button",
        "id": "track",
        "title": "Track order",
        "description": "",
    }
    for message in (unknown, text, outbound):
        assert results[str(message.pk)]["reply"] is None


def test_malformed_reply_payloads_are_null(auth_client, conversation):
    broken = [
        MessageFactory(
            conversation=conversation, inbound=True, type=Message.Type.INTERACTIVE, payload=payload
        )
        for payload in (
            {},
            {"interactive": "junk"},
            {"interactive": {"type": "button_reply", "button_reply": "junk"}},
        )
    ]
    broken.append(
        MessageFactory(
            conversation=conversation, inbound=True, type=Message.Type.BUTTON, payload={}
        )
    )

    results = results_by_id(auth_client(Role.VIEWER), conversation)

    assert [results[str(message.pk)]["reply"] for message in broken] == [None] * 4


# --- order_id -----------------------------------------------------------------------------------


def test_order_id_from_source_ref(auth_client, conversation):
    order_id = uuid.uuid4()
    notification = MessageFactory(
        conversation=conversation, source=Message.Source.COMMERCE, source_ref=f"order:{order_id}"
    )
    linked_cart = cart(conversation, "KAJU", source_ref=f"order:{order_id}")
    shop = MessageFactory(
        conversation=conversation, source=Message.Source.COMMERCE, source_ref="shop"
    )
    bad_ref = MessageFactory(
        conversation=conversation, source=Message.Source.COMMERCE, source_ref="order:not-a-uuid"
    )
    campaign = MessageFactory(
        conversation=conversation, source=Message.Source.CAMPAIGN, source_ref=str(uuid.uuid4())
    )
    bad_reply = interactive_reply(
        conversation, "button_reply", {"id": "upc:ord:view:nope", "title": "View order"}
    )

    results = results_by_id(auth_client(Role.VIEWER), conversation)

    assert results[str(notification.pk)]["order_id"] == str(order_id)
    assert results[str(linked_cart.pk)]["order_id"] == str(order_id)
    for message in (shop, bad_ref, campaign, bad_reply):
        assert results[str(message.pk)]["order_id"] is None


# --- product names ------------------------------------------------------------------------------


def test_cart_items_carry_product_names(auth_client, workspace, conversation, other_workspace):
    ProductFactory(workspace=workspace, sku="KAJU", name="Kaju Katli 250 g")
    ProductFactory(workspace=other_workspace, sku="LADDU", name="Other workspace laddu")
    message = cart(conversation, "KAJU", "LADDU", "GONE")

    results = results_by_id(auth_client(Role.VIEWER), conversation)

    items = results[str(message.pk)]["order"]["items"]
    assert [(item["product_retailer_id"], item["name"]) for item in items] == [
        ("KAJU", "Kaju Katli 250 g"),
        ("LADDU", None),
        ("GONE", None),
    ]


def test_product_names_are_one_query_for_the_page(auth_client, workspace, conversation):
    for index in range(3):
        ProductFactory(workspace=workspace, sku=f"SKU-A{index}")
    client = auth_client(Role.VIEWER)
    cart(conversation, "SKU-A0")

    with CaptureQueriesContext(connection) as one_cart:
        assert client.get(messages_url(conversation)).status_code == 200
    for index in range(1, 3):
        cart(conversation, f"SKU-A{index}", "SKU-A0")
    with CaptureQueriesContext(connection) as three_carts:
        response = client.get(messages_url(conversation))

    assert len(three_carts.captured_queries) == len(one_cart.captured_queries)
    names = [
        item["name"]
        for message in response.json()["results"]
        for item in (message["order"] or {}).get("items", [])
    ]
    assert len(names) == 5
    assert None not in names


def test_single_message_serializer_looks_up_names(workspace):
    conversation = ConversationFactory(workspace=workspace)
    ProductFactory(workspace=workspace, sku="KAJU", name="Kaju Katli")
    message = cart(conversation, "KAJU")

    data = MessageSerializer(message).data

    assert data["order"]["items"][0]["name"] == "Kaju Katli"
    assert data["reply"] is None
    assert data["order_id"] is None


def test_messages_of_another_workspace_are_hidden(auth_client, conversation, other_workspace):
    message = cart(conversation, "KAJU")
    client = auth_client(workspace=other_workspace)

    assert client.get(messages_url(conversation)).status_code == 404
    assert str(message.pk) not in str(client.get("/api/v1/inbox/conversations/").content)
