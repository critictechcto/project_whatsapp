"""Inbound offer codes: claiming, claims, replies and the MessageRecorded wiring."""

import pytest

from apps.inbox.models import Message
from apps.offers import services
from apps.offers.models import OfferClaim
from apps.orders import services as order_services
from common import events
from common.commerce import is_claimed_by_commerce

from .conftest import recorded_event

pytestmark = pytest.mark.django_db

REFERRAL = {
    "source_url": "https://fb.me/abc123",
    "source_id": "120210000000001",
    "source_type": "ad",
    "headline": "Diwali sweets: 10% off",
    "body": "Order on WhatsApp",
    "ctwa_clid": "ARAkLkA8rmlFeiCktEJQ",
}


def offer_replies():
    return list(
        Message.objects.filter(
            direction=Message.Direction.OUTBOUND, source_ref__startswith="offer:"
        ).order_by("created_at", "pk")
    )


@pytest.fixture
def checkout_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        order_services,
        "apply_offer_to_active_checkout",
        lambda conversation_id: calls.append(conversation_id) or False,
    )
    return calls


# --- Claimer ------------------------------------------------------------------------------------


def test_code_messages_are_claimed_by_commerce(offer, inbound):
    event = recorded_event(inbound(" diwali! "))
    assert services.is_offer_message(event) is True
    assert is_claimed_by_commerce(event) is True


def test_other_messages_are_not_claimed(offer, inbound):
    assert services.is_offer_message(recorded_event(inbound("hello there"))) is False
    assert services.is_offer_message(recorded_event(inbound("DIWALI please"))) is False


def test_outbound_and_non_text_are_not_claimed(offer, conversation):
    from apps.inbox.factories import MessageFactory

    outbound = MessageFactory(conversation=conversation, text="DIWALI")
    image = MessageFactory(conversation=conversation, inbound=True, type="image", text="DIWALI")
    assert services.is_offer_message(recorded_event(outbound)) is False
    assert services.is_offer_message(recorded_event(image)) is False


def test_codes_are_not_claimed_without_commerce(offer, inbound, no_commerce):
    assert services.is_offer_message(recorded_event(inbound())) is False


# --- Claims and replies -------------------------------------------------------------------------


def test_code_records_a_claim_and_replies(offer, inbound, contact, conversation, checkout_calls):
    message = inbound("Diwali")

    result = services.handle_code_message(message.pk)

    claim = OfferClaim.objects.get()
    assert result.created is True
    assert claim.offer == offer
    assert claim.contact == contact
    assert claim.conversation == conversation
    assert claim.message == message
    assert claim.wamid == message.wamid
    assert claim.status == OfferClaim.Status.CLAIMED
    assert claim.ad_source_id == "" and claim.ctwa_clid == ""
    [reply] = offer_replies()
    assert reply.source == Message.Source.COMMERCE
    assert reply.source_ref == f"offer:{offer.pk}"
    assert reply.type == Message.Type.TEXT
    assert reply.text == offer.reply_text
    assert checkout_calls == [conversation.pk]


def test_retry_is_a_no_op(offer, inbound, checkout_calls):
    message = inbound()

    services.handle_code_message(message.pk)
    second = services.handle_code_message(message.pk)

    assert second.created is False
    assert OfferClaim.objects.count() == 1
    assert len(offer_replies()) == 1


def test_click_to_whatsapp_referral_is_captured(offer, inbound, checkout_calls):
    message = inbound(payload={"type": "text", "referral": REFERRAL})

    services.handle_code_message(message.pk)

    claim = OfferClaim.objects.get()
    assert claim.ad_source_id == REFERRAL["source_id"]
    assert claim.ad_source_url == REFERRAL["source_url"]
    assert claim.ad_headline == REFERRAL["headline"]
    assert claim.ctwa_clid == REFERRAL["ctwa_clid"]
    assert claim.from_ad is True


def test_per_contact_limit_resends_the_reply(offer, inbound, checkout_calls):
    services.handle_code_message(inbound().pk)
    result = services.handle_code_message(inbound("diwali").pk)

    assert result.created is False
    assert OfferClaim.objects.count() == 1
    assert len(offer_replies()) == 2
    assert all(reply.text == offer.reply_text for reply in offer_replies())


def test_per_contact_limit_above_one_allows_more_claims(offer, inbound, checkout_calls):
    offer.max_uses_per_contact = 2
    offer.save()

    services.handle_code_message(inbound().pk)
    services.handle_code_message(inbound().pk)
    services.handle_code_message(inbound().pk)

    assert OfferClaim.objects.count() == 2


def test_fully_used_offer_says_so(offer, inbound, checkout_calls):
    from apps.offers.factories import OfferClaimFactory

    offer.max_uses = 1
    offer.save()
    OfferClaimFactory(offer=offer, status=OfferClaim.Status.REDEEMED)

    result = services.handle_code_message(inbound().pk)

    assert result.claim is None
    assert OfferClaim.objects.count() == 1
    [reply] = offer_replies()
    assert reply.text == services.FULLY_CLAIMED_TEXT
    assert checkout_calls == []


def test_store_with_products_adds_shop_buttons(offer, inbound, store, product, checkout_calls):
    services.handle_code_message(inbound().pk)

    [reply] = offer_replies()
    assert reply.type == Message.Type.INTERACTIVE
    interactive = reply.payload["interactive"]
    assert interactive["body"]["text"] == offer.reply_text
    buttons = [(b["reply"]["id"], b["reply"]["title"]) for b in interactive["action"]["buttons"]]
    assert buttons == [("upc:shop:browse", "Shop now"), ("upc:shop:menu", "Menu")]


def test_store_without_items_sends_plain_text(offer, inbound, store, checkout_calls):
    services.handle_code_message(inbound().pk)
    assert offer_replies()[0].type == Message.Type.TEXT


def test_disabled_store_sends_plain_text(offer, inbound, store, product, checkout_calls):
    store.enabled = False
    store.save()
    services.handle_code_message(inbound().pk)
    assert offer_replies()[0].type == Message.Type.TEXT


def test_only_services_say_book_now(offer, inbound, store, product, checkout_calls):
    if not hasattr(product, "kind"):
        pytest.skip("Product.kind is added by the catalog branch")
    product.kind = "service"
    product.save()

    services.handle_code_message(inbound().pk)

    titles = [
        b["reply"]["title"] for b in offer_replies()[0].payload["interactive"]["action"]["buttons"]
    ]
    assert titles == ["Book now", "Menu"]


def test_nothing_happens_without_commerce(offer, inbound, no_commerce, checkout_calls):
    assert services.handle_code_message(inbound().pk) is None
    assert not OfferClaim.objects.exists()
    assert offer_replies() == []


# --- Wiring -------------------------------------------------------------------------------------


def test_message_recorded_queues_the_task(
    offer, inbound, checkout_calls, django_capture_on_commit_callbacks
):
    message = inbound()

    with django_capture_on_commit_callbacks(execute=True):
        events.emit(events.message_recorded, recorded_event(message))
    with django_capture_on_commit_callbacks(execute=True):
        events.emit(events.message_recorded, recorded_event(message))

    assert OfferClaim.objects.count() == 1
    assert len(offer_replies()) == 1


def test_other_messages_queue_nothing(offer, inbound, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        events.emit(events.message_recorded, recorded_event(inbound("hello")))
    assert not OfferClaim.objects.exists()
