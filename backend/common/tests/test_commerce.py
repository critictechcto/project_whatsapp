import uuid
from datetime import UTC, datetime

import pytest

from common import commerce
from common.events import MessageRecorded


def make_event(**overrides) -> MessageRecorded:
    fields = {
        "workspace_id": uuid.uuid4(),
        "message_id": uuid.uuid4(),
        "conversation_id": uuid.uuid4(),
        "contact_id": uuid.uuid4(),
        "phone_number_id": uuid.uuid4(),
        "direction": "inbound",
        "source": "inbound",
        "source_ref": "",
        "type": "text",
        "text": "hello",
        "reply_id": None,
        "wamid": "wamid.X",
        "is_first_inbound": False,
        "contact_created": False,
        "created_at": datetime(2026, 9, 14, tzinfo=UTC),
    }
    return MessageRecorded(**{**fields, **overrides})


def test_build_and_parse_round_trip():
    product_id = uuid.uuid4()

    reply_id = commerce.build_reply_id("shop", "add", product_id, 2)

    assert reply_id == f"upc:shop:add:{product_id}:2"
    parsed = commerce.parse_reply_id(reply_id)
    assert parsed == commerce.ReplyId("shop", "add", (str(product_id), "2"))
    assert str(parsed) == reply_id


@pytest.mark.parametrize(
    "value",
    [None, 42, "", "shop:add", "upc:", "upc:shop", "upc:unknown:x", "upc:shop:add:a b", "x" * 201],
)
def test_parse_rejects_malformed_ids(value):
    assert commerce.parse_reply_id(value) is None


@pytest.mark.parametrize(
    ("scope", "action", "args"),
    [("nope", "x", ()), ("shop", "a:b", ()), ("shop", "add", ("",)), ("shop", "x", ("y" * 200,))],
)
def test_build_rejects_invalid_parts(scope, action, args):
    with pytest.raises(ValueError):
        commerce.build_reply_id(scope, action, *args)


def test_claims_carts_and_commerce_replies_only_for_inbound():
    assert commerce.is_claimed_by_commerce(make_event(type="order", text="Cart"))
    assert commerce.is_claimed_by_commerce(make_event(type="interactive", reply_id="upc:nfm:x"))
    assert not commerce.is_claimed_by_commerce(make_event(type="button", reply_id="Yes"))
    assert not commerce.is_claimed_by_commerce(make_event())
    assert not commerce.is_claimed_by_commerce(make_event(direction="outbound", type="order"))


def test_registered_claimers_and_failures():
    def claim_menu(event):
        return event.text == "menu"

    def broken(event):
        raise RuntimeError("boom")

    commerce.register_message_claimer(broken)
    commerce.register_message_claimer(claim_menu)
    commerce.register_message_claimer(claim_menu)
    try:
        assert commerce.is_claimed_by_commerce(make_event(text="menu"))
        assert not commerce.is_claimed_by_commerce(make_event(text="hello"))
    finally:
        commerce.unregister_message_claimer(broken)
        commerce.unregister_message_claimer(claim_menu)

    assert not commerce.is_claimed_by_commerce(make_event(text="menu"))
