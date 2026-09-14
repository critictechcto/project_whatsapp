"""Inbox API: listing and sending messages, policy errors, idempotency and notes."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.contacts.factories import ContactFactory
from apps.contacts.models import Contact
from apps.inbox.factories import (
    ConversationFactory,
    ConversationNoteFactory,
    MediaAssetFactory,
    MessageFactory,
)
from apps.inbox.models import ConversationNote, Message
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount
from common.roles import Role

pytestmark = pytest.mark.django_db

BASE = "/api/v1/inbox/conversations/"


def messages_url(conversation) -> str:
    return f"{BASE}{conversation.pk}/messages/"


def notes_url(conversation) -> str:
    return f"{BASE}{conversation.pk}/notes/"


def post_message(client, conversation, body, **extra):
    return client.post(messages_url(conversation), body, format="json", **extra)


def walk(client, url) -> list[str]:
    seen = []
    while url:
        body = client.get(url).json()
        seen.extend(item["id"] for item in body["results"])
        url = body["next"]
    return seen


# --- List ---------------------------------------------------------------------------------------


def test_messages_are_newest_first_and_paginated(auth_client, conversation):
    now = timezone.now()
    messages = [MessageFactory(conversation=conversation) for _ in range(5)]
    for index, message in enumerate(messages):
        Message.objects.filter(pk=message.pk).update(created_at=now - timedelta(minutes=index))
    same_moment = MessageFactory(conversation=conversation)
    Message.objects.filter(pk=same_moment.pk).update(created_at=now - timedelta(minutes=2))
    MessageFactory()  # another conversation
    client = auth_client(Role.VIEWER)

    seen = walk(client, f"{messages_url(conversation)}?page_size=2")

    assert len(seen) == len(set(seen)) == 6
    assert seen[0] == str(messages[0].pk)
    assert seen[-1] == str(messages[4].pk)
    full = client.get(messages_url(conversation)).json()["results"]
    assert [item["id"] for item in full] == seen


def test_message_shape(auth_client, conversation, template, user):
    inbound = MessageFactory(conversation=conversation, inbound=True, text="Where is my order?")
    reply = MessageFactory(
        conversation=conversation,
        type=Message.Type.TEMPLATE,
        template=template,
        template_name=template.name,
        template_language="en",
        text="Hi Asha",
        sent_by=user,
        reply_to=inbound,
        reply_to_wamid=inbound.wamid,
        status=Message.Status.FAILED,
        error_code="131026",
        error_message="Message undeliverable",
    )
    image = MessageFactory(
        conversation=conversation,
        inbound=True,
        type=Message.Type.IMAGE,
        mime_type="image/jpeg",
        file_name="photo.jpg",
        size=11,
        file=ContentFile(b"\xff\xd8\xff jpeg!", name="photo.jpg"),
    )
    pending_image = MessageFactory(
        conversation=conversation, inbound=True, type=Message.Type.IMAGE, media_id="999"
    )

    results = {
        item["id"]: item
        for item in auth_client(Role.VIEWER).get(messages_url(conversation)).json()["results"]
    }

    item = results[str(reply.pk)]
    assert item["conversation_id"] == str(conversation.pk)
    assert item["template"] == {"id": str(template.pk), "name": template.name, "language": "en"}
    assert item["reply_to_message_id"] == str(inbound.pk)
    assert item["sent_by"] == {"id": str(user.pk), "full_name": user.full_name, "email": user.email}
    assert (item["status"], item["error_code"], item["error_message"]) == (
        "failed",
        "131026",
        "Message undeliverable",
    )
    assert item["media"] is None
    assert item["source"] == "inbox"

    item = results[str(inbound.pk)]
    assert (item["direction"], item["status"], item["template"], item["sent_by"]) == (
        "inbound",
        "received",
        None,
        None,
    )
    assert item["error_code"] == ""

    media = results[str(image.pk)]["media"]
    assert media["mime_type"] == "image/jpeg"
    assert media["file_name"] == "photo.jpg"
    assert media["size"] == 11
    assert media["download_url"] == f"http://testserver/api/v1/inbox/messages/{image.pk}/media/"
    assert results[str(pending_image.pk)]["media"]["download_url"] is None


def test_queued_message_without_wamid_serializes_empty_string(auth_client, conversation):
    MessageFactory(conversation=conversation, wamid=None, status=Message.Status.QUEUED)

    [item] = auth_client().get(messages_url(conversation)).json()["results"]

    assert item["wamid"] == ""


# --- Send ---------------------------------------------------------------------------------------


def test_send_text(auth_client, workspace, conversation, fake_graph, user, commit):
    client = auth_client(Role.AGENT)

    with commit():
        response = post_message(client, conversation, {"type": "text", "text": "Shipped today!"})

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "queued"
    assert body["type"] == "text"
    assert body["text"] == "Shipped today!"
    assert body["source"] == "inbox"
    assert body["direction"] == "outbound"
    assert body["conversation_id"] == str(conversation.pk)
    message = Message.objects.get(pk=body["id"])
    assert body["sent_by"]["id"] == str(message.sent_by_id)
    assert message.sent_by_id != user.pk  # the agent client's own user
    assert message.idempotency_key is None
    # Dispatched on commit through the fake Graph client.
    assert message.status == Message.Status.SENT
    assert len(fake_graph.sent_messages) == 1


def test_idempotency_key_replay_returns_the_same_message(auth_client, conversation):
    client = auth_client(Role.AGENT)
    body = {"type": "text", "text": "Your refund is processed."}

    first = post_message(client, conversation, body, HTTP_IDEMPOTENCY_KEY="retry-1")
    second = post_message(client, conversation, body, HTTP_IDEMPOTENCY_KEY="retry-1")
    changed = post_message(
        client, conversation, {"type": "text", "text": "Different"}, HTTP_IDEMPOTENCY_KEY="retry-1"
    )
    other = post_message(client, conversation, body, HTTP_IDEMPOTENCY_KEY="retry-2")

    assert first.status_code == second.status_code == changed.status_code == 201
    assert first.json()["id"] == second.json()["id"] == changed.json()["id"]
    assert other.json()["id"] != first.json()["id"]
    assert Message.objects.filter(conversation=conversation).count() == 2
    assert Message.objects.get(pk=first.json()["id"]).idempotency_key == "inbox:retry-1"


@pytest.mark.parametrize("key", ["has space", "x" * 201, "tab\tkey"])
def test_invalid_idempotency_key(auth_client, conversation, key):
    response = post_message(
        auth_client(Role.AGENT),
        conversation,
        {"type": "text", "text": "Hi"},
        HTTP_IDEMPOTENCY_KEY=key,
    )

    assert response.status_code == 400
    assert "idempotency_key" in response.json()["error"]["details"]


def test_send_template(auth_client, conversation, template):
    response = post_message(
        auth_client(Role.AGENT),
        conversation,
        {"type": "template", "template_id": str(template.pk), "body_params": ["Asha", "UC-1"]},
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["type"] == "template"
    assert body["template"] == {
        "id": str(template.pk),
        "name": template.name,
        "language": template.language,
    }
    assert body["text"] == "Hi Asha, your order UC-1 has shipped."


def test_template_parameters_are_validated(auth_client, conversation, template):
    response = post_message(
        auth_client(Role.AGENT),
        conversation,
        {"type": "template", "template_id": str(template.pk), "body_params": ["only one"]},
    )

    assert response.status_code == 400


def test_template_must_belong_to_the_workspace(auth_client, conversation, other_workspace):
    foreign = MessageTemplateFactory(
        waba__workspace=other_workspace, status=MessageTemplate.Status.APPROVED
    )
    client = auth_client(Role.AGENT)

    for template_id in (foreign.pk, uuid.uuid4()):
        response = post_message(
            client, conversation, {"type": "template", "template_id": str(template_id)}
        )
        assert response.status_code == 400
        assert "template_id" in response.json()["error"]["details"]
    assert not Message.objects.filter(conversation=conversation).exists()


def test_send_media(auth_client, workspace, conversation):
    asset = MediaAssetFactory(workspace=workspace)

    response = post_message(
        auth_client(Role.AGENT),
        conversation,
        {"type": "media", "media_id": str(asset.pk), "caption": "Your invoice"},
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["type"] == "image"
    assert body["text"] == "Your invoice"
    assert body["media"]["mime_type"] == "image/jpeg"
    assert body["media"]["download_url"].endswith(f"/api/v1/inbox/messages/{body['id']}/media/")


def test_media_must_belong_to_the_workspace(auth_client, conversation, other_workspace):
    foreign = MediaAssetFactory(workspace=other_workspace)
    client = auth_client(Role.AGENT)

    for media_id in (foreign.pk, uuid.uuid4()):
        response = post_message(client, conversation, {"type": "media", "media_id": str(media_id)})
        assert response.status_code == 400
        assert "media_id" in response.json()["error"]["details"]


def test_reply_to_message_resolves_the_wamid(auth_client, conversation):
    target = MessageFactory(conversation=conversation, inbound=True)

    response = post_message(
        auth_client(Role.AGENT),
        conversation,
        {"type": "text", "text": "Noted", "reply_to_message_id": str(target.pk)},
    )

    assert response.status_code == 201, response.content
    assert response.json()["reply_to_message_id"] == str(target.pk)
    message = Message.objects.get(pk=response.json()["id"])
    assert message.reply_to_wamid == target.wamid
    assert message.payload["context"] == {"message_id": target.wamid}


def test_reply_to_must_be_an_accepted_message_in_the_conversation(
    auth_client, workspace, conversation
):
    elsewhere = MessageFactory(conversation=ConversationFactory(workspace=workspace))
    queued = MessageFactory(conversation=conversation, wamid=None, status=Message.Status.QUEUED)
    client = auth_client(Role.AGENT)

    for target in (elsewhere.pk, queued.pk, uuid.uuid4()):
        response = post_message(
            client,
            conversation,
            {"type": "text", "text": "Noted", "reply_to_message_id": str(target)},
        )
        assert response.status_code == 400
        assert "reply_to_message_id" in response.json()["error"]["details"]


@pytest.fixture
def ctx(workspace, number, contact, conversation, template):
    return SimpleNamespace(
        workspace=workspace,
        number=number,
        contact=contact,
        conversation=conversation,
        template=template,
    )


def _template_body(template):
    return {"type": "template", "template_id": str(template.pk), "body_params": ["A", "B"]}


def _outside_window(ctx):
    contact = ContactFactory(workspace=ctx.workspace)
    conversation = ConversationFactory(
        workspace=ctx.workspace, contact=contact, phone_number=ctx.number
    )
    return conversation, {"type": "text", "text": "Hello again"}


def _opted_out(ctx):
    contact = ContactFactory(
        workspace=ctx.workspace,
        marketing_opt_in_status=Contact.OptInStatus.OPTED_OUT,
        opted_out_at=timezone.now() - timedelta(days=1),
    )
    conversation = ConversationFactory(
        workspace=ctx.workspace, contact=contact, phone_number=ctx.number
    )
    return conversation, _template_body(ctx.template)


def _marketing_without_opt_in(ctx):
    template = MessageTemplateFactory(
        waba=ctx.number.waba,
        status=MessageTemplate.Status.APPROVED,
        category=MessageTemplate.Category.MARKETING,
    )
    contact = ContactFactory(workspace=ctx.workspace)
    conversation = ConversationFactory(
        workspace=ctx.workspace, contact=contact, phone_number=ctx.number
    )
    return conversation, _template_body(template)


def _template_not_approved(ctx):
    template = MessageTemplateFactory(waba=ctx.number.waba, status=MessageTemplate.Status.DRAFT)
    return ctx.conversation, _template_body(template)


def _not_connected(ctx):
    WhatsAppBusinessAccount.objects.filter(pk=ctx.number.waba_id).update(
        status=WhatsAppBusinessAccount.Status.DISCONNECTED
    )
    return ctx.conversation, {"type": "text", "text": "Hi"}


def _not_registered(ctx):
    PhoneNumber.objects.filter(pk=ctx.number.pk).update(
        registration_status=PhoneNumber.RegistrationStatus.PENDING
    )
    return ctx.conversation, {"type": "text", "text": "Hi"}


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        (_outside_window, "outside_service_window"),
        (_opted_out, "contact_opted_out"),
        (_marketing_without_opt_in, "marketing_opt_in_required"),
        (_template_not_approved, "template_not_approved"),
        (_not_connected, "whatsapp_not_connected"),
        (_not_registered, "phone_number_not_registered"),
    ],
)
def test_policy_errors_are_409(auth_client, ctx, setup, code):
    conversation, body = setup(ctx)

    response = post_message(auth_client(Role.AGENT), conversation, body)

    assert response.status_code == 409, response.content
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert not Message.objects.filter(conversation=conversation, source="inbox").exists()


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"type": "text"}, "text"),
        ({"type": "text", "text": "   "}, "text"),
        ({"type": "template"}, "template_id"),
        ({"type": "media"}, "media_id"),
        ({"type": "location"}, "type"),
        (
            {"type": "template", "template_id": str(uuid.uuid4()), "button_params": {"x": "1"}},
            "button_params",
        ),
    ],
)
def test_send_message_validation(auth_client, conversation, body, field):
    response = post_message(auth_client(Role.AGENT), conversation, body)

    assert response.status_code == 400, response.content
    assert field in response.json()["error"]["details"]


# --- Notes --------------------------------------------------------------------------------------


def test_notes_list_newest_first(auth_client, conversation, user):
    now = timezone.now()
    old = ConversationNoteFactory(conversation=conversation, author=user, body="First call")
    new = ConversationNoteFactory(conversation=conversation, author=user, body="Second call")
    ConversationNote.objects.filter(pk=old.pk).update(created_at=now - timedelta(hours=1))
    ConversationNoteFactory()  # another workspace's conversation

    body = auth_client(Role.VIEWER).get(notes_url(conversation)).json()

    assert [item["id"] for item in body["results"]] == [str(new.pk), str(old.pk)]
    assert body["results"][0]["author"] == {
        "id": str(user.pk),
        "full_name": user.full_name,
        "email": user.email,
    }
    assert body["results"][0]["body"] == "Second call"


def test_create_note(auth_client, conversation):
    response = auth_client(Role.AGENT).post(
        notes_url(conversation), {"body": "  Prefers Hindi.  "}, format="json"
    )

    assert response.status_code == 201, response.content
    assert response.json()["body"] == "Prefers Hindi."
    note = ConversationNote.objects.get(pk=response.json()["id"])
    assert note.conversation == conversation
    assert response.json()["author"]["id"] == str(note.author_id)


def test_blank_note_is_rejected(auth_client, conversation):
    response = auth_client(Role.AGENT).post(notes_url(conversation), {"body": "  "}, format="json")

    assert response.status_code == 400
    assert "body" in response.json()["error"]["details"]
