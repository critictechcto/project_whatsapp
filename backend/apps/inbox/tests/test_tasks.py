from datetime import timedelta

import pytest
from django.utils import timezone

from apps.contacts import services as contact_services
from apps.contacts.factories import ContactFactory
from apps.contacts.models import ConsentEvent
from apps.inbox import interactive, sending
from apps.inbox.factories import ConversationFactory, MediaAssetFactory, MessageFactory
from apps.inbox.limiter import override_limiter
from apps.inbox.models import Message
from apps.inbox.tasks import (
    MAX_SEND_RETRIES,
    dispatch_message,
    download_media,
    fail_stuck_messages,
)
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.client.errors import (
    InvalidParameterError,
    NetworkError,
    OutsideWindowError,
    RateLimitedError,
    TransientError,
    error_from_response,
)
from common.events import MessageDeliveryUpdated

pytestmark = pytest.mark.django_db


def queue_text(conversation, body="Hello"):
    return sending.send_message(
        workspace=conversation.workspace,
        contact=conversation.contact,
        content=sending.TextContent(body),
        conversation=conversation,
        source=Message.Source.CAMPAIGN,
        source_ref="campaign-7",
        dispatch=False,
    )


def run(message, **options):
    return dispatch_message.apply(args=[str(message.pk)], throw=False, **options)


def test_second_dispatch_is_a_no_op(conversation, fake_graph, commit, recorded):
    message = queue_text(conversation)

    with commit():
        assert run(message).get() == Message.Status.SENT
        assert run(message).get() is None

    assert len(fake_graph.calls_to("send_message")) == 1
    assert [e.status for e in recorded.of(MessageDeliveryUpdated)] == ["sent"]


def test_message_claimed_by_another_worker_is_skipped(conversation, fake_graph):
    message = queue_text(conversation)
    Message.objects.filter(pk=message.pk).update(status=Message.Status.SENDING)

    assert run(message).get() is None

    assert fake_graph.calls_to("send_message") == []


def test_network_error_marks_unknown_and_is_not_retried(conversation, fake_graph, commit, recorded):
    message = queue_text(conversation)
    fake_graph.fail("send_message", NetworkError("Read timed out"))

    with commit():
        run(message)

    message.refresh_from_db()
    assert message.status == Message.Status.FAILED
    assert message.error_code == "network_unknown"
    assert message.failed_at is not None
    assert message.wamid is None
    assert len(fake_graph.calls_to("send_message")) == 1
    [event] = recorded.of(MessageDeliveryUpdated)
    assert (event.status, event.error_code) == ("failed", "network_unknown")
    assert (event.source, event.source_ref) == ("campaign", "campaign-7")
    assert event.conversation_id == conversation.pk


def test_retryable_error_is_retried(conversation, fake_graph, commit):
    message = queue_text(conversation)
    fake_graph.fail("send_message", TransientError("Service unavailable", code=131000))

    with commit():
        run(message)

    message.refresh_from_db()
    assert message.status == Message.Status.SENT
    assert len(fake_graph.calls_to("send_message")) == 2


def test_retry_gives_the_message_back_to_the_queue(conversation, fake_graph):
    message = queue_text(conversation)
    fake_graph.fail("send_message", RateLimitedError("Too many messages", code=130429), times=2)

    # The last allowed retry: releases, retries once more, then gives up.
    run(message, retries=MAX_SEND_RETRIES - 1)

    message.refresh_from_db()
    assert message.status == Message.Status.FAILED
    assert message.error_code == "130429"
    assert len(fake_graph.calls_to("send_message")) == 2


def test_non_retryable_error_fails_with_meta_code(conversation, fake_graph, commit, recorded):
    message = queue_text(conversation)
    fake_graph.fail("send_message", OutsideWindowError("Re-engagement message", code=131047))

    with commit():
        run(message)

    message.refresh_from_db()
    assert message.status == Message.Status.FAILED
    assert message.error_code == "131047"
    assert message.error_message == "Re-engagement message"
    assert [e.error_code for e in recorded.of(MessageDeliveryUpdated)] == ["131047"]


def test_unsupported_interactive_fails_with_1026(conversation, fake_graph, commit, recorded):
    message = sending.send_message(
        workspace=conversation.workspace,
        contact=conversation.contact,
        content=interactive.address_message("Where should we deliver?"),
        conversation=conversation,
        source=Message.Source.AUTOMATION,
        dispatch=False,
    )
    error = error_from_response(
        400, {"error": {"code": 1026, "message": "Receiver incapable", "type": "OAuthException"}}
    )
    assert error.retryable is False
    fake_graph.fail("send_message", error)

    with commit():
        run(message)

    message.refresh_from_db()
    assert (message.status, message.error_code) == (Message.Status.FAILED, "1026")
    assert len(fake_graph.calls_to("send_message")) == 1
    assert [e.error_code for e in recorded.of(MessageDeliveryUpdated)] == ["1026"]


def test_response_without_wamid_fails(conversation, fake_graph, monkeypatch):
    message = queue_text(conversation)
    monkeypatch.setattr(fake_graph, "send_message", lambda phone_number_id, body: {"messages": []})

    run(message)

    message.refresh_from_db()
    assert (message.status, message.error_code) == ("failed", "invalid_response")


# --- Policy re-checked at dispatch -------------------------------------------------------------


def test_opt_out_after_queueing_blocks_dispatch(conversation, fake_graph, commit, recorded):
    message = queue_text(conversation)
    contact_services.record_opt_out(
        conversation.contact, source=ConsentEvent.Source.WHATSAPP_KEYWORD
    )

    with commit():
        run(message)

    message.refresh_from_db()
    assert (message.status, message.error_code) == ("failed", "contact_opted_out")
    assert fake_graph.calls_to("send_message") == []
    assert [e.status for e in recorded.of(MessageDeliveryUpdated)] == ["failed"]


def test_window_closing_before_dispatch_blocks_free_form(conversation, fake_graph):
    message = queue_text(conversation)
    conversation.service_window_expires_at = timezone.now() - timedelta(seconds=1)
    conversation.save()

    run(message)

    message.refresh_from_db()
    assert (message.status, message.error_code) == ("failed", "outside_service_window")


def queue_template(workspace, contact, template):
    return sending.send_message(
        workspace=workspace,
        contact=contact,
        content=sending.TemplateContent(template, ["a", "b"]),
        source=Message.Source.AUTOMATION,
        dispatch=False,
    )


def test_template_paused_before_dispatch_fails(workspace, contact, number, template, fake_graph):
    message = queue_template(workspace, contact, template)
    template.status = MessageTemplate.Status.PAUSED
    template.save()

    run(message)

    message.refresh_from_db()
    assert (message.status, message.error_code) == ("failed", "template_not_approved")
    assert fake_graph.calls_to("send_message") == []


def test_template_deleted_before_dispatch_fails(workspace, contact, number, template, fake_graph):
    message = queue_template(workspace, contact, template)
    template.delete()

    run(message)

    message.refresh_from_db()
    assert (message.status, message.error_code) == ("failed", "template_not_approved")


def test_template_recategorised_as_marketing_needs_opt_in(workspace, number, template, fake_graph):
    unknown = ContactFactory(workspace=workspace)
    message = queue_template(workspace, unknown, template)
    template.category = MessageTemplate.Category.MARKETING
    template.save()

    run(message)

    message.refresh_from_db()
    assert (message.status, message.error_code) == ("failed", "marketing_opt_in_required")


# --- Rate limiting and media -------------------------------------------------------------------


class DenyOnce:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def acquire(self, key: str) -> float:
        self.keys.append(key)
        return 0.5 if len(self.keys) == 1 else 0.0


def test_rate_limited_message_is_requeued(conversation, fake_graph):
    message = queue_text(conversation)
    limiter = DenyOnce()

    with override_limiter(limiter):
        run(message)

    message.refresh_from_db()
    assert message.status == Message.Status.SENT
    assert limiter.keys == [conversation.phone_number.phone_number_id] * 2
    assert len(fake_graph.calls_to("send_message")) == 1


def test_media_upload_network_error_is_safe_to_retry(workspace, conversation, fake_graph):
    asset = MediaAssetFactory(workspace=workspace)
    message = sending.send_message(
        workspace=workspace,
        contact=conversation.contact,
        content=sending.MediaContent(asset),
        source=Message.Source.INBOX,
        dispatch=False,
    )
    fake_graph.fail("upload_media", NetworkError("Connection reset"))

    run(message)

    message.refresh_from_db()
    assert message.status == Message.Status.SENT
    assert len(fake_graph.calls_to("upload_media")) == 2
    assert len(fake_graph.calls_to("send_message")) == 1


def test_deleted_media_fails_the_message(workspace, conversation, fake_graph):
    asset = MediaAssetFactory(workspace=workspace)
    message = sending.send_message(
        workspace=workspace,
        contact=conversation.contact,
        content=sending.MediaContent(asset),
        source=Message.Source.INBOX,
        dispatch=False,
    )
    asset.delete()

    run(message)

    message.refresh_from_db()
    assert (message.status, message.error_code) == ("failed", "media_unavailable")


def test_fail_stuck_messages(conversation, commit, recorded):
    stuck = MessageFactory(conversation=conversation, status=Message.Status.SENDING, wamid=None)
    Message.objects.filter(pk=stuck.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    fresh = MessageFactory(conversation=conversation, status=Message.Status.SENDING, wamid=None)

    with commit():
        assert fail_stuck_messages() == 1

    stuck.refresh_from_db()
    fresh.refresh_from_db()
    assert (stuck.status, stuck.error_code) == ("failed", "network_unknown")
    assert fresh.status == Message.Status.SENDING
    assert [e.message_id for e in recorded.of(MessageDeliveryUpdated)] == [stuck.pk]


def inbound_image(conversation, fake_graph, content=b"png-bytes"):
    media_id = fake_graph.upload_media(
        conversation.phone_number.phone_number_id,
        content=content,
        mime_type="image/png",
        filename="x.png",
    )["id"]
    return MessageFactory(
        conversation=conversation,
        inbound=True,
        type=Message.Type.IMAGE,
        media_id=media_id,
        mime_type="image/png",
    )


def test_download_media_stores_the_file_once(conversation, fake_graph):
    message = inbound_image(conversation, fake_graph)

    stored = download_media.apply(args=[str(message.pk)]).get()
    again = download_media.apply(args=[str(message.pk)]).get()

    message.refresh_from_db()
    assert stored == message.file.name
    assert stored.endswith(".png")
    assert message.file.read() == b"png-bytes"
    assert message.size == len(b"png-bytes")
    assert again is None
    assert len(fake_graph.calls_to("get_media")) == 1


def test_download_media_retries_transient_errors(conversation, fake_graph):
    message = inbound_image(conversation, fake_graph)
    fake_graph.fail("get_media", TransientError("Temporarily unavailable", code=2))

    download_media.apply(args=[str(message.pk)], throw=False)

    message.refresh_from_db()
    assert message.file
    assert len(fake_graph.calls_to("get_media")) == 2


def test_download_media_gives_up_on_permanent_errors(conversation, fake_graph):
    message = inbound_image(conversation, fake_graph)
    fake_graph.fail("get_media", InvalidParameterError("Media not found", code=100))

    assert download_media.apply(args=[str(message.pk)]).get() is None

    message.refresh_from_db()
    assert not message.file


def test_download_media_for_other_conversation_types_is_skipped(fake_graph):
    message = MessageFactory(conversation=ConversationFactory(), inbound=True)

    assert download_media.apply(args=[str(message.pk)]).get() is None
    assert fake_graph.calls_to("get_media") == []
