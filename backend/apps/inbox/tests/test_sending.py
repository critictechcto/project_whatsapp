from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.contacts.factories import ContactFactory
from apps.contacts.models import Contact
from apps.inbox import sending
from apps.inbox.factories import ConversationFactory, MediaAssetFactory, MessageFactory
from apps.inbox.models import Conversation, Message
from apps.message_templates import services as template_services
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.factories import PhoneNumberFactory, WhatsAppBusinessAccountFactory
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount
from common.events import MessageDeliveryUpdated, MessageRecorded
from common.exceptions import Conflict

pytestmark = pytest.mark.django_db


def send(workspace, contact, content, **kwargs):
    kwargs.setdefault("source", Message.Source.INBOX)
    return sending.send_message(workspace=workspace, contact=contact, content=content, **kwargs)


def text(body="Your order has shipped."):
    return sending.TextContent(body)


def assert_policy_error(exc_info, code: str) -> None:
    assert isinstance(exc_info.value, Conflict)
    assert exc_info.value.status_code == 409
    assert exc_info.value.get_codes() == code


# --- Happy paths -------------------------------------------------------------------------------


def test_text_in_open_window_is_queued_then_sent(
    workspace, contact, conversation, user, fake_graph, commit, recorded
):
    with commit():
        message = send(workspace, contact, text(), sent_by=user)
        assert message.status == Message.Status.QUEUED
        assert fake_graph.calls_to("send_message") == []
        assert recorded.events == []

    message.refresh_from_db()
    assert message.status == Message.Status.SENT
    assert message.wamid.startswith("wamid.FAKE")
    assert message.sent_at is not None
    assert message.conversation == conversation
    assert (message.direction, message.type, message.source) == ("outbound", "text", "inbox")
    assert message.sent_by == user
    assert fake_graph.sent_messages == [
        {
            "phone_number_id": conversation.phone_number.phone_number_id,
            "wamid": message.wamid,
            "to": contact.wa_id,
            "type": "text",
            "text": {"body": "Your order has shipped.", "preview_url": False},
        }
    ]
    [created] = recorded.of(MessageRecorded)
    assert created.message_id == message.pk
    assert created.conversation_id == conversation.pk
    assert created.contact_id == contact.pk
    assert created.phone_number_id == conversation.phone_number_id
    assert (created.direction, created.source, created.type) == ("outbound", "inbox", "text")
    assert created.is_first_inbound is False
    assert created.contact_created is False
    [delivery] = recorded.of(MessageDeliveryUpdated)
    assert (delivery.message_id, delivery.status, delivery.error_code) == (message.pk, "sent", "")
    conversation.refresh_from_db()
    assert conversation.last_message_at is not None


def test_dispatch_false_waits_for_enqueue(workspace, contact, conversation, fake_graph, commit):
    with commit():
        message = send(workspace, contact, text(), dispatch=False)
    message.refresh_from_db()
    assert message.status == Message.Status.QUEUED
    assert fake_graph.calls_to("send_message") == []

    with commit():
        sending.enqueue([message.pk])

    message.refresh_from_db()
    assert message.status == Message.Status.SENT


def test_template_can_be_sent_outside_the_window(
    workspace, contact, number, template, fake_graph, commit
):
    with commit():
        message = send(
            workspace,
            contact,
            sending.TemplateContent(template, body_params=["Priya", "A-102"]),
            source=Message.Source.CAMPAIGN,
            source_ref="campaign-1",
        )

    message.refresh_from_db()
    assert message.status == Message.Status.SENT
    assert message.type == Message.Type.TEMPLATE
    assert message.text == "Hi Priya, your order A-102 has shipped."
    assert message.template == template
    assert (message.template_name, message.template_language, message.template_category) == (
        template.name,
        "en",
        "UTILITY",
    )
    parameters = [{"type": "text", "text": "Priya"}, {"type": "text", "text": "A-102"}]
    assert message.template_components == [{"type": "body", "parameters": parameters}]
    [sent] = fake_graph.sent_messages
    assert sent["type"] == "template"
    assert sent["template"] == {
        "name": template.name,
        "language": {"code": "en"},
        "components": [{"type": "body", "parameters": parameters}],
    }
    conversation = Conversation.objects.get(contact=contact, phone_number=number)
    assert conversation.service_window_expires_at is None


def test_window_open(workspace, contact, number):
    assert sending.window_open(contact, number) is False

    conversation = ConversationFactory(
        workspace=workspace, contact=contact, phone_number=number, window_open=True
    )
    assert sending.window_open(contact, number) is True

    conversation.service_window_expires_at = timezone.now() - timedelta(seconds=1)
    conversation.save()
    assert sending.window_open(contact, number) is False


def test_window_is_per_phone_number(workspace, contact, conversation):
    other_number = PhoneNumberFactory(workspace=workspace, waba=conversation.phone_number.waba)

    assert sending.window_open(contact, conversation.phone_number) is True
    assert sending.window_open(contact, other_number) is False


def test_default_number_is_used_when_none_given(workspace, contact, number, template):
    PhoneNumberFactory(workspace=workspace, waba=number.waba)  # not default

    message = send(
        workspace, contact, sending.TemplateContent(template, ["a", "b"]), dispatch=False
    )

    assert message.conversation.phone_number == number


def test_explicit_phone_number_gets_its_own_conversation(
    workspace, contact, conversation, template
):
    second = PhoneNumberFactory(workspace=workspace, waba=conversation.phone_number.waba)

    message = send(
        workspace,
        contact,
        sending.TemplateContent(template, ["a", "b"]),
        phone_number=second,
        dispatch=False,
    )

    assert message.conversation.phone_number == second
    assert message.conversation != conversation
    assert Conversation.objects.filter(contact=contact).count() == 2


def test_reply_to_wamid_sets_context(workspace, contact, conversation, fake_graph, commit):
    inbound = MessageFactory(conversation=conversation, inbound=True)

    with commit():
        message = send(
            workspace,
            contact,
            text("Sure"),
            conversation=conversation,
            reply_to_wamid=inbound.wamid,
        )

    assert message.reply_to == inbound
    assert message.reply_to_wamid == inbound.wamid
    assert fake_graph.sent_messages[0]["context"] == {"message_id": inbound.wamid}


# --- Policy ------------------------------------------------------------------------------------


def test_free_form_outside_window_is_rejected(workspace, contact, number):
    ConversationFactory(
        workspace=workspace,
        contact=contact,
        phone_number=number,
        service_window_expires_at=timezone.now() - timedelta(minutes=1),
    )

    with pytest.raises(sending.OutsideServiceWindow) as exc_info:
        send(workspace, contact, text())

    assert_policy_error(exc_info, "outside_service_window")
    assert not Message.objects.exists()


def test_free_form_without_any_conversation_is_rejected(workspace, contact, number):
    with pytest.raises(sending.OutsideServiceWindow):
        send(workspace, contact, text())

    assert not Conversation.objects.exists()


def test_opted_out_contact_cannot_get_templates(workspace, number, template):
    contact = ContactFactory(
        workspace=workspace,
        marketing_opt_in_status=Contact.OptInStatus.OPTED_OUT,
        opted_out_at=timezone.now() - timedelta(days=1),
    )
    ConversationFactory(workspace=workspace, contact=contact, phone_number=number, window_open=True)

    with pytest.raises(sending.ContactOptedOut) as exc_info:
        send(workspace, contact, sending.TemplateContent(template, ["a", "b"]))

    assert_policy_error(exc_info, "contact_opted_out")


def test_opted_out_contact_gets_replies_only_after_writing_again(workspace, number):
    opted_out_at = timezone.now() - timedelta(hours=2)
    contact = ContactFactory(
        workspace=workspace,
        marketing_opt_in_status=Contact.OptInStatus.OPTED_OUT,
        opted_out_at=opted_out_at,
    )
    conversation = ConversationFactory(
        workspace=workspace,
        contact=contact,
        phone_number=number,
        last_inbound_at=opted_out_at,  # the STOP message itself
        service_window_expires_at=opted_out_at + timedelta(hours=24),
    )

    with pytest.raises(sending.ContactOptedOut):
        send(workspace, contact, text())

    conversation.last_inbound_at = timezone.now() - timedelta(hours=1)
    conversation.save()

    message = send(workspace, contact, text(), dispatch=False)
    assert message.status == Message.Status.QUEUED


def test_marketing_template_requires_opt_in(workspace, number):
    marketing = MessageTemplateFactory(
        waba=number.waba,
        status=MessageTemplate.Status.APPROVED,
        category=MessageTemplate.Category.MARKETING,
    )
    unknown = ContactFactory(workspace=workspace)

    with pytest.raises(sending.MarketingOptInRequired) as exc_info:
        send(workspace, unknown, sending.TemplateContent(marketing, ["a", "b"]))
    assert_policy_error(exc_info, "marketing_opt_in_required")

    opted_in = ContactFactory(
        workspace=workspace, marketing_opt_in_status=Contact.OptInStatus.OPTED_IN
    )
    message = send(workspace, opted_in, sending.TemplateContent(marketing, ["a", "b"]))
    assert message.template_category == "MARKETING"


def test_utility_template_does_not_need_opt_in(workspace, number, template):
    unknown = ContactFactory(workspace=workspace)

    message = send(
        workspace, unknown, sending.TemplateContent(template, ["a", "b"]), dispatch=False
    )

    assert message.status == Message.Status.QUEUED


@pytest.mark.parametrize(
    "status",
    [
        MessageTemplate.Status.DRAFT,
        MessageTemplate.Status.PENDING,
        MessageTemplate.Status.REJECTED,
        MessageTemplate.Status.PAUSED,
        MessageTemplate.Status.DISABLED,
    ],
)
def test_unapproved_template_is_rejected(workspace, contact, number, status):
    template = MessageTemplateFactory(waba=number.waba, status=status)

    with pytest.raises(sending.TemplateNotApproved) as exc_info:
        send(workspace, contact, sending.TemplateContent(template, ["a", "b"]))

    assert_policy_error(exc_info, "template_not_approved")
    assert isinstance(exc_info.value, template_services.TemplateNotApproved)
    assert isinstance(exc_info.value, sending.SendPolicyError)
    assert not Message.objects.exists()


def test_template_from_another_account_is_invalid(workspace, contact, number):
    other_waba = WhatsAppBusinessAccountFactory(workspace=workspace)
    template = MessageTemplateFactory(waba=other_waba, status=MessageTemplate.Status.APPROVED)

    with pytest.raises(ValidationError) as exc_info:
        send(workspace, contact, sending.TemplateContent(template, ["a", "b"]))

    assert "template_id" in exc_info.value.detail


def test_template_parameters_are_validated(workspace, contact, number, template):
    with pytest.raises(ValidationError) as exc_info:
        send(workspace, contact, sending.TemplateContent(template, ["only one"]))

    assert "body_params" in exc_info.value.detail


def test_account_must_be_connected(workspace, contact, conversation):
    waba = conversation.phone_number.waba
    waba.status = WhatsAppBusinessAccount.Status.DISCONNECTED
    waba.save()

    with pytest.raises(sending.WhatsAppNotConnected) as exc_info:
        send(workspace, contact, text(), conversation=conversation)

    assert_policy_error(exc_info, "whatsapp_not_connected")


def test_number_must_be_registered_unless_coexistence(workspace, contact, conversation):
    phone = conversation.phone_number
    phone.registration_status = PhoneNumber.RegistrationStatus.PENDING
    phone.save()

    with pytest.raises(sending.PhoneNumberNotRegistered) as exc_info:
        send(workspace, contact, text(), conversation=conversation)
    assert_policy_error(exc_info, "phone_number_not_registered")

    phone.is_coexistence = True
    phone.save()
    message = send(workspace, contact, text(), conversation=conversation, dispatch=False)
    assert message.status == Message.Status.QUEUED


def test_workspace_without_default_number_is_not_connected(workspace, contact):
    with pytest.raises(sending.WhatsAppNotConnected):
        send(workspace, contact, text())


# --- Idempotency -------------------------------------------------------------------------------


def test_same_idempotency_key_returns_existing_message(
    workspace, contact, conversation, fake_graph, commit
):
    with commit():
        first = send(workspace, contact, text(), idempotency_key="inbox:client-1")
    # Even though policy would now reject a new message, the key returns the original.
    conversation.service_window_expires_at = timezone.now() - timedelta(minutes=1)
    conversation.save()

    with commit():
        again = send(workspace, contact, text("changed"), idempotency_key="inbox:client-1")

    assert again.pk == first.pk
    assert Message.objects.count() == 1
    assert len(fake_graph.calls_to("send_message")) == 1


def test_idempotency_keys_are_scoped_to_the_workspace(workspace, other_workspace, conversation):
    other = ConversationFactory(workspace=other_workspace, window_open=True)
    key = "inbox:same-key"

    mine = send(workspace, conversation.contact, text(), idempotency_key=key, dispatch=False)
    theirs = send(
        other_workspace,
        other.contact,
        text(),
        conversation=other,
        idempotency_key=key,
        dispatch=False,
    )

    assert mine.pk != theirs.pk
    assert Message.objects.filter(idempotency_key=key).count() == 2


def test_idempotency_race_returns_the_winning_message(
    workspace, contact, conversation, monkeypatch
):
    key = "campaign:c1:recipient:r1"
    winner = MessageFactory(
        conversation=conversation, idempotency_key=key, status=Message.Status.QUEUED, wamid=None
    )
    lookups = []
    real_lookup = sending._find_by_idempotency_key

    def miss_first_lookup(ws, idempotency_key):
        lookups.append(idempotency_key)
        return None if len(lookups) == 1 else real_lookup(ws, idempotency_key)

    monkeypatch.setattr(sending, "_find_by_idempotency_key", miss_first_lookup)

    result = send(workspace, contact, text(), idempotency_key=key, dispatch=False)

    assert result.pk == winner.pk
    assert lookups == [key, key]
    assert Message.objects.filter(idempotency_key=key).count() == 1


# --- Media -------------------------------------------------------------------------------------


def test_media_is_uploaded_once_per_number_and_reused(
    workspace, contact, conversation, fake_graph, commit
):
    asset = MediaAssetFactory(workspace=workspace)

    with commit():
        first = send(workspace, contact, sending.MediaContent(asset, caption="Invoice photo"))
    with commit():
        second = send(workspace, contact, sending.MediaContent(asset))

    first.refresh_from_db()
    second.refresh_from_db()
    asset.refresh_from_db()
    assert (first.status, second.status) == ("sent", "sent")
    assert (first.type, first.text, first.mime_type) == ("image", "Invoice photo", "image/jpeg")
    assert first.media_asset == asset
    assert len(fake_graph.calls_to("upload_media")) == 1
    assert asset.meta_media_id
    assert asset.meta_phone_number_id == conversation.phone_number.phone_number_id
    assert fake_graph.sent_messages[0]["image"] == {
        "caption": "Invoice photo",
        "id": asset.meta_media_id,
    }
    assert fake_graph.sent_messages[1]["image"] == {"id": asset.meta_media_id}


def test_document_sends_its_file_name(workspace, contact, conversation, fake_graph, commit):
    asset = MediaAssetFactory(
        workspace=workspace, mime_type="application/pdf", file_name="invoice.pdf"
    )

    with commit():
        message = send(workspace, contact, sending.MediaContent(asset))

    assert message.type == Message.Type.DOCUMENT
    assert fake_graph.sent_messages[0]["document"]["filename"] == "invoice.pdf"


def test_audio_cannot_have_a_caption(workspace, contact, conversation):
    asset = MediaAssetFactory(workspace=workspace, mime_type="audio/ogg", file_name="note.ogg")

    with pytest.raises(ValidationError) as exc_info:
        send(workspace, contact, sending.MediaContent(asset, caption="hi"))

    assert "caption" in exc_info.value.detail


def test_media_from_another_workspace_is_invalid(workspace, other_workspace, contact, conversation):
    asset = MediaAssetFactory(workspace=other_workspace)

    with pytest.raises(ValidationError):
        send(workspace, contact, sending.MediaContent(asset))


@pytest.mark.parametrize(
    ("mime_type", "expected"),
    [
        ("image/png", "image"),
        ("image/webp", "sticker"),
        ("video/mp4", "video"),
        ("audio/mpeg", "audio"),
        ("application/pdf", "document"),
        ("", "document"),
    ],
)
def test_media_type_for(mime_type, expected):
    assert sending.media_type_for(mime_type) == expected


# --- Input guards ------------------------------------------------------------------------------


def test_contact_from_another_workspace_is_a_programming_error(
    workspace, other_workspace, conversation
):
    stranger = ContactFactory(workspace=other_workspace)

    with pytest.raises(ValueError, match="workspace"):
        send(workspace, stranger, text())


def test_conversation_must_match_contact(workspace, conversation):
    other_contact = ContactFactory(workspace=workspace)

    with pytest.raises(ValueError, match="conversation"):
        send(workspace, other_contact, text(), conversation=conversation)


def test_inbound_source_is_rejected(workspace, contact, conversation):
    with pytest.raises(ValueError, match="source"):
        send(workspace, contact, text(), source=Message.Source.INBOUND)


def test_blank_text_is_invalid(workspace, contact, conversation):
    with pytest.raises(ValidationError) as exc_info:
        send(workspace, contact, text("   "))

    assert "text" in exc_info.value.detail
