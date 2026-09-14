from datetime import timedelta

import pytest
from django.utils import timezone

from apps.contacts.factories import ContactFactory
from apps.contacts.models import Contact
from apps.inbox import sending
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import Conversation, Message
from apps.inbox.receivers import StatusForUnknownMessage, on_message_status
from apps.whatsapp.factories import PhoneNumberFactory
from common.events import (
    InboundMessage,
    MessageDeliveryUpdated,
    MessageRecorded,
    MessageStatus,
    MetaError,
    emit,
    inbound_message_received,
    message_status_updated,
)

pytestmark = pytest.mark.django_db

WA_ID = "919876543210"


def seconds_ago(seconds: int):
    return timezone.now().replace(microsecond=0) - timedelta(seconds=seconds)


def inbound(number, *, wamid="wamid.IN1", text="Hi", type="text", timestamp=None, **kwargs):
    return InboundMessage(
        workspace_id=number.workspace_id,
        waba_id=number.waba.waba_id,
        phone_number_id=number.phone_number_id,
        wamid=wamid,
        from_wa_id=kwargs.pop("from_wa_id", WA_ID),
        timestamp=timestamp or seconds_ago(5),
        type=type,
        text=text,
        profile_name=kwargs.pop("profile_name", "Priya Sharma"),
        **kwargs,
    )


def status(message, value, *, timestamp=None, **kwargs):
    return MessageStatus(
        workspace_id=kwargs.pop("workspace_id", message.workspace_id),
        waba_id="waba",
        phone_number_id=kwargs.pop("phone_number_id", "phone"),
        wamid=kwargs.pop("wamid", message.wamid),
        recipient_wa_id=WA_ID,
        status=value,
        timestamp=timestamp or seconds_ago(1),
        **kwargs,
    )


def deliver(signal, event) -> None:
    assert emit(signal, event) == []


def receive(event) -> None:
    deliver(inbound_message_received, event)


# --- Inbound messages ---------------------------------------------------------------------------


def test_inbound_message_creates_conversation_and_message(number, commit, recorded):
    sent_at = seconds_ago(300)

    with commit():
        receive(inbound(number, timestamp=sent_at))

    contact = Contact.objects.get(workspace=number.workspace, phone_e164=f"+{WA_ID}")
    conversation = Conversation.objects.get(contact=contact, phone_number=number)
    assert conversation.status == Conversation.Status.OPEN
    assert conversation.unread_count == 1
    assert conversation.last_inbound_at == sent_at
    assert conversation.last_message_at == sent_at
    assert conversation.service_window_expires_at == sent_at + timedelta(hours=24)
    assert sending.window_open(contact, number)

    message = conversation.messages.get()
    assert (message.direction, message.status, message.source) == (
        "inbound",
        "received",
        "inbound",
    )
    assert (message.type, message.text, message.wamid) == ("text", "Hi", "wamid.IN1")
    assert message.sent_at == sent_at
    assert message.workspace == number.workspace

    [event] = recorded.of(MessageRecorded)
    assert event.workspace_id == number.workspace_id
    assert event.message_id == message.pk
    assert event.conversation_id == conversation.pk
    assert event.contact_id == contact.pk
    assert event.phone_number_id == number.pk
    assert (event.direction, event.source, event.type, event.text) == (
        "inbound",
        "inbound",
        "text",
        "Hi",
    )
    assert event.wamid == "wamid.IN1"
    assert event.is_first_inbound is True
    assert event.contact_created is True


def test_events_wait_for_commit(number, django_capture_on_commit_callbacks, recorded):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        receive(inbound(number))

    assert recorded.events == []
    assert callbacks


def test_redelivery_is_idempotent(number, commit, recorded):
    event = inbound(number)

    with commit():
        receive(event)
        receive(event)
    with commit():
        receive(event)

    assert Message.objects.count() == 1
    assert Conversation.objects.get().unread_count == 1
    assert len(recorded.of(MessageRecorded)) == 1


def test_later_messages_are_not_first_inbound(number, commit, recorded):
    with commit():
        receive(inbound(number, wamid="wamid.IN1", timestamp=seconds_ago(20)))
        receive(inbound(number, wamid="wamid.IN2", timestamp=seconds_ago(10)))

    first, second = recorded.of(MessageRecorded)
    assert (first.is_first_inbound, first.contact_created) == (True, True)
    assert (second.is_first_inbound, second.contact_created) == (False, False)
    assert Conversation.objects.get().unread_count == 2


def test_known_contact_is_not_reported_as_created(number, commit, recorded):
    contact = ContactFactory(workspace=number.workspace, phone_e164=f"+{WA_ID}", wa_id=WA_ID)
    Contact.objects.filter(pk=contact.pk).update(created_at=timezone.now() - timedelta(days=30))

    with commit():
        receive(inbound(number))

    [event] = recorded.of(MessageRecorded)
    assert event.contact_id == contact.pk
    assert event.contact_created is False
    assert event.is_first_inbound is True


def test_inbound_reopens_a_closed_conversation(number, commit):
    contact = ContactFactory(workspace=number.workspace, phone_e164=f"+{WA_ID}", wa_id=WA_ID)
    conversation = ConversationFactory(
        workspace=number.workspace,
        contact=contact,
        phone_number=number,
        status=Conversation.Status.CLOSED,
    )

    with commit():
        receive(inbound(number))

    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.OPEN
    assert conversation.unread_count == 1


def test_older_message_arriving_late_does_not_shrink_the_window(number, commit):
    newer, older = seconds_ago(60), seconds_ago(7200)

    with commit():
        receive(inbound(number, wamid="wamid.NEW", timestamp=newer))
        receive(inbound(number, wamid="wamid.OLD", timestamp=older))

    conversation = Conversation.objects.get()
    assert conversation.last_inbound_at == newer
    assert conversation.last_message_at == newer
    assert conversation.service_window_expires_at == newer + timedelta(hours=24)
    assert conversation.unread_count == 2


def test_system_message_does_not_open_the_window(number, commit):
    with commit():
        receive(inbound(number, type="system", text=None))

    conversation = Conversation.objects.get()
    assert conversation.service_window_expires_at is None
    assert conversation.unread_count == 0
    assert conversation.messages.get().type == Message.Type.UNSUPPORTED


def test_unknown_types_are_stored_as_unsupported(number, commit):
    payload = {"id": "wamid.ORDER", "type": "order", "order": {"catalog_id": "1"}}

    with commit():
        receive(inbound(number, wamid="wamid.ORDER", type="order", text=None, payload=payload))

    message = Message.objects.get()
    assert message.type == Message.Type.UNSUPPORTED
    assert message.payload == payload


def test_reply_context_links_the_original_message(number, commit, recorded):
    outbound = MessageFactory(
        conversation=ConversationFactory(workspace=number.workspace, phone_number=number)
    )

    with commit():
        receive(
            inbound(
                number,
                type="button",
                text="Track order",
                reply_id="track-order",
                context_wamid=outbound.wamid,
            )
        )

    message = Message.objects.get(wamid="wamid.IN1")
    assert message.reply_to == outbound
    assert message.reply_to_wamid == outbound.wamid
    assert message.type == Message.Type.BUTTON
    [event] = recorded.of(MessageRecorded)
    assert event.reply_id == "track-order"


def test_inbound_media_is_downloaded(number, fake_graph, commit):
    media_id = fake_graph.upload_media(
        number.phone_number_id, content=b"voice-note", mime_type="audio/ogg", filename="a.ogg"
    )["id"]
    payload = {"type": "audio", "audio": {"id": media_id, "mime_type": "audio/ogg; codecs=opus"}}

    with commit():
        receive(inbound(number, type="audio", text=None, payload=payload))

    message = Message.objects.get()
    assert message.type == Message.Type.AUDIO
    assert message.media_id == media_id
    assert message.mime_type == "audio/ogg; codecs=opus"
    assert message.file.read() == b"voice-note"


def test_message_for_an_unknown_number_is_ignored(number, commit):
    event = InboundMessage(
        workspace_id=number.workspace_id,
        waba_id="waba",
        phone_number_id="999999",
        wamid="wamid.X",
        from_wa_id=WA_ID,
        timestamp=seconds_ago(1),
        type="text",
        text="hi",
    )

    with commit():
        receive(event)

    assert not Message.objects.exists()
    assert not Conversation.objects.exists()


def test_inbound_messages_are_tenant_isolated(number, other_workspace, commit):
    other_number = PhoneNumberFactory(workspace=other_workspace, waba__workspace=other_workspace)
    spoofed = InboundMessage(
        workspace_id=other_workspace.pk,  # routed to another workspace than the number's
        waba_id="waba",
        phone_number_id=number.phone_number_id,
        wamid="wamid.SPOOF",
        from_wa_id=WA_ID,
        timestamp=seconds_ago(1),
        type="text",
        text="hi",
    )

    with commit():
        receive(inbound(number, wamid="wamid.MINE"))
        receive(inbound(other_number, wamid="wamid.THEIRS"))
        receive(spoofed)

    mine = Conversation.objects.for_workspace(number.workspace).get()
    theirs = Conversation.objects.for_workspace(other_workspace).get()
    assert mine.phone_number == number
    assert theirs.phone_number == other_number
    assert mine.contact != theirs.contact
    assert [m.wamid for m in Message.objects.for_workspace(number.workspace)] == ["wamid.MINE"]
    assert [m.wamid for m in Message.objects.for_workspace(other_workspace)] == ["wamid.THEIRS"]


# --- Delivery statuses -------------------------------------------------------------------------


@pytest.fixture
def outbound(conversation):
    return MessageFactory(
        conversation=conversation,
        status=Message.Status.SENT,
        sent_at=seconds_ago(60),
        source=Message.Source.CAMPAIGN,
        source_ref="campaign-1",
    )


def statuses(recorded) -> list[str]:
    return [event.status for event in recorded.of(MessageDeliveryUpdated)]


def test_status_progression(outbound, commit, recorded):
    delivered_at, read_at = seconds_ago(30), seconds_ago(10)

    with commit():
        deliver(message_status_updated, status(outbound, "delivered", timestamp=delivered_at))
        deliver(message_status_updated, status(outbound, "read", timestamp=read_at))

    outbound.refresh_from_db()
    assert outbound.status == Message.Status.READ
    assert (outbound.delivered_at, outbound.read_at) == (delivered_at, read_at)
    assert statuses(recorded) == ["delivered", "read"]
    event = recorded.of(MessageDeliveryUpdated)[-1]
    assert (event.source, event.source_ref, event.error_code) == ("campaign", "campaign-1", "")
    assert event.message_id == outbound.pk
    assert event.conversation_id == outbound.conversation_id
    assert event.occurred_at == read_at


def test_out_of_order_statuses_never_go_backwards(outbound, commit, recorded):
    with commit():
        deliver(message_status_updated, status(outbound, "read", timestamp=seconds_ago(10)))
        deliver(message_status_updated, status(outbound, "delivered", timestamp=seconds_ago(20)))
        deliver(message_status_updated, status(outbound, "sent", timestamp=seconds_ago(30)))

    outbound.refresh_from_db()
    assert outbound.status == Message.Status.READ
    assert outbound.read_at is not None
    assert outbound.delivered_at is not None
    assert statuses(recorded) == ["read"]


def test_duplicate_status_is_emitted_once(outbound, commit, recorded):
    event = status(outbound, "delivered")

    with commit():
        deliver(message_status_updated, event)
        deliver(message_status_updated, event)

    assert statuses(recorded) == ["delivered"]


def test_failed_status_records_the_error(outbound, commit, recorded):
    error = MetaError(
        code=131026, title="Message undeliverable", details="Recipient is not on WhatsApp."
    )

    with commit():
        deliver(message_status_updated, status(outbound, "failed", errors=(error,)))

    outbound.refresh_from_db()
    assert outbound.status == Message.Status.FAILED
    assert outbound.error_code == "131026"
    assert outbound.error_message == "Recipient is not on WhatsApp."
    assert outbound.failed_at is not None
    [event] = recorded.of(MessageDeliveryUpdated)
    assert (event.status, event.error_code) == ("failed", "131026")


def test_later_delivery_wins_over_failed(outbound, commit, recorded):
    error = MetaError(code=131000, title="Something went wrong")

    with commit():
        deliver(message_status_updated, status(outbound, "failed", errors=(error,)))
        deliver(message_status_updated, status(outbound, "sent"))
        deliver(message_status_updated, status(outbound, "delivered"))

    outbound.refresh_from_db()
    assert outbound.status == Message.Status.DELIVERED
    assert (outbound.error_code, outbound.error_message, outbound.failed_at) == ("", "", None)
    assert statuses(recorded) == ["failed", "delivered"]


def test_failed_after_read_is_ignored(outbound, commit, recorded):
    with commit():
        deliver(message_status_updated, status(outbound, "read"))
        deliver(message_status_updated, status(outbound, "failed"))

    outbound.refresh_from_db()
    assert outbound.status == Message.Status.READ
    assert outbound.error_code == ""
    assert statuses(recorded) == ["read"]


def test_received_messages_are_never_overwritten(conversation, commit, recorded):
    inbound_message = MessageFactory(conversation=conversation, inbound=True)

    with commit():
        deliver(message_status_updated, status(inbound_message, "read"))

    inbound_message.refresh_from_db()
    assert inbound_message.status == Message.Status.RECEIVED
    assert recorded.events == []


def test_pricing_is_recorded(outbound):
    deliver(
        message_status_updated,
        status(outbound, "delivered", pricing_category="utility", billable=True),
    )

    outbound.refresh_from_db()
    assert (outbound.pricing_category, outbound.billable) == ("utility", True)


def test_unknown_status_values_are_ignored(outbound):
    deliver(message_status_updated, status(outbound, "warning"))

    outbound.refresh_from_db()
    assert outbound.status == Message.Status.SENT


def test_recent_status_while_a_message_is_sending_asks_for_a_retry(conversation):
    MessageFactory(conversation=conversation, status=Message.Status.SENDING, wamid=None)
    event = MessageStatus(
        workspace_id=conversation.workspace_id,
        waba_id="waba",
        phone_number_id=conversation.phone_number.phone_number_id,
        wamid="wamid.NOT_YET",
        recipient_wa_id=WA_ID,
        status="delivered",
        timestamp=seconds_ago(5),
    )

    with pytest.raises(StatusForUnknownMessage):
        on_message_status(sender=MessageStatus, event=event)
    failures = emit(message_status_updated, event)
    assert any(isinstance(exc, StatusForUnknownMessage) for _, exc in failures)


def test_recent_status_for_unknown_wamid_with_nothing_sending_is_ignored(conversation):
    MessageFactory(conversation=conversation, status=Message.Status.QUEUED, wamid=None)
    other_number = PhoneNumberFactory(
        workspace=conversation.workspace, waba=conversation.phone_number.waba
    )
    MessageFactory(
        conversation=ConversationFactory(
            workspace=conversation.workspace,
            contact=conversation.contact,
            phone_number=other_number,
        ),
        status=Message.Status.SENDING,
        wamid=None,
    )
    event = MessageStatus(
        workspace_id=conversation.workspace_id,
        waba_id="waba",
        phone_number_id=conversation.phone_number.phone_number_id,
        wamid="wamid.SENT_ELSEWHERE",
        recipient_wa_id=WA_ID,
        status="delivered",
        timestamp=seconds_ago(5),
    )

    assert emit(message_status_updated, event) == []


def test_old_status_for_unknown_wamid_is_ignored(workspace):
    event = MessageStatus(
        workspace_id=workspace.pk,
        waba_id="waba",
        phone_number_id="phone",
        wamid="wamid.FOREIGN",
        recipient_wa_id=WA_ID,
        status="delivered",
        timestamp=timezone.now() - timedelta(minutes=11),
    )

    on_message_status(sender=MessageStatus, event=event)  # no exception


def test_status_arriving_before_the_wamid_is_stored(
    conversation, fake_graph, monkeypatch, commit, recorded
):
    message = sending.send_message(
        workspace=conversation.workspace,
        contact=conversation.contact,
        content=sending.TextContent("Hello"),
        conversation=conversation,
        source=Message.Source.INBOX,
        dispatch=False,
    )
    early = status(
        message,
        "delivered",
        wamid="wamid.EARLY",
        phone_number_id=conversation.phone_number.phone_number_id,
    )
    failures = []

    def send_and_race_the_webhook(phone_number_id, body):
        # Meta's status webhook arrives before the task has stored the wamid.
        failures.extend(emit(message_status_updated, early))
        return {"messages": [{"id": "wamid.EARLY"}]}

    monkeypatch.setattr(fake_graph, "send_message", send_and_race_the_webhook)
    with commit():
        sending.enqueue([message.pk])
    assert [type(exc) for _, exc in failures] == [StatusForUnknownMessage]

    with commit():
        deliver(message_status_updated, early)  # the webhook retry

    message.refresh_from_db()
    assert (message.wamid, message.status) == ("wamid.EARLY", "delivered")
    assert statuses(recorded) == ["sent", "delivered"]


def test_statuses_are_tenant_isolated(outbound, other_workspace):
    foreign = status(
        outbound,
        "read",
        workspace_id=other_workspace.pk,
        timestamp=timezone.now() - timedelta(minutes=11),
    )

    deliver(message_status_updated, foreign)

    outbound.refresh_from_db()
    assert outbound.status == Message.Status.SENT
    assert outbound.read_at is None
