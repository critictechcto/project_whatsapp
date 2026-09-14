"""Send WhatsApp messages from any app (inbox API, campaigns, automations).

:func:`send_message` runs the policy checks synchronously, stores a ``queued`` Message and, on
commit, enqueues ``inbox.dispatch_message``, which re-checks policy before calling Meta.

Policy errors subclass :class:`SendPolicyError` (a 409 ``common.exceptions.Conflict``):

- ``whatsapp_not_connected``: no default number, or the number's WABA must reconnect.
- ``phone_number_not_registered``: the number is not registered for the Cloud API.
- ``contact_opted_out``: the contact opted out. Templates are always blocked; free-form replies
  are allowed only after the customer wrote again following the opt-out.
- ``outside_service_window``: free-form message more than 24h after the customer's last message.
- ``marketing_opt_in_required``: MARKETING templates need a recorded opt-in.
- ``template_not_approved``: only APPROVED templates can be sent.
"""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.contacts.models import Contact
from apps.message_templates import services as template_services
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.models import PhoneNumber
from common.exceptions import Conflict

from . import services
from .models import Conversation, MediaAsset, Message

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024


# --- Content ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextContent:
    body: str
    preview_url: bool = False


@dataclass(frozen=True, slots=True)
class TemplateContent:
    template: MessageTemplate
    body_params: Sequence[str] = ()
    header_param: str | Mapping[str, Any] | None = None
    button_params: Mapping[int, str] | None = None


@dataclass(frozen=True, slots=True)
class MediaContent:
    asset: MediaAsset
    caption: str = ""


@dataclass(frozen=True, slots=True)
class InteractiveContent:
    """A raw Cloud API ``interactive`` object; ``summary`` is the text shown in the inbox.

    Build these with the helpers in :mod:`apps.inbox.interactive`, which enforce Meta's limits.
    Interactive messages are session messages: outside the 24-hour window ``send_message``
    raises :class:`OutsideServiceWindow`.
    """

    interactive: Mapping[str, Any]
    summary: str


Content = TextContent | TemplateContent | MediaContent | InteractiveContent


# --- Errors -------------------------------------------------------------------------------------


class SendPolicyError(Conflict):
    default_code = "send_not_allowed"
    default_detail = "This message cannot be sent."


class WhatsAppNotConnected(SendPolicyError):
    default_code = "whatsapp_not_connected"
    default_detail = "Connect a WhatsApp number before sending messages."


class PhoneNumberNotRegistered(SendPolicyError):
    default_code = "phone_number_not_registered"
    default_detail = "This WhatsApp number is not registered for sending yet."


class OutsideServiceWindow(SendPolicyError):
    default_code = "outside_service_window"
    default_detail = (
        "More than 24 hours have passed since the customer's last message. "
        "Send an approved template instead."
    )


class ContactOptedOut(SendPolicyError):
    default_code = "contact_opted_out"
    default_detail = "This contact has opted out of messages from this business."


class MarketingOptInRequired(SendPolicyError):
    default_code = "marketing_opt_in_required"
    default_detail = "Marketing templates can only be sent to contacts who opted in."


class TemplateNotApproved(SendPolicyError, template_services.TemplateNotApproved):
    """Also a ``message_templates.services.TemplateNotApproved``."""

    default_code = "template_not_approved"
    default_detail = "Only approved templates can be sent."


# --- Public API ---------------------------------------------------------------------------------


def window_open(contact: Contact, phone_number: PhoneNumber) -> bool:
    """True while the 24-hour customer service window for ``(contact, phone_number)`` is open."""
    return Conversation.objects.filter(
        workspace_id=contact.workspace_id,
        contact=contact,
        phone_number=phone_number,
        service_window_expires_at__gt=timezone.now(),
    ).exists()


def enqueue(message_ids: Iterable[UUID]) -> None:
    """Dispatch queued messages after the current transaction commits (immediately outside one).

    Messages that are no longer ``queued`` are skipped by the task.
    """
    from .tasks import dispatch_message

    for message_id in message_ids:
        transaction.on_commit(partial(dispatch_message.delay, str(message_id)), robust=True)


def send_message(
    *,
    workspace,
    contact: Contact,
    content: Content,
    conversation: Conversation | None = None,
    phone_number: PhoneNumber | None = None,
    reply_to_wamid: str | None = None,
    source: str,
    source_ref: str = "",
    sent_by=None,
    idempotency_key: str | None = None,
    dispatch: bool = True,
) -> Message:
    """Check policy, store a ``queued`` outbound Message and dispatch it on commit.

    The same ``idempotency_key`` in a workspace returns the existing Message without any checks.
    """
    if idempotency_key is not None:
        existing = _find_by_idempotency_key(workspace, idempotency_key)
        if existing is not None:
            return existing

    if source not in Message.Source.values or source == Message.Source.INBOUND:
        raise ValueError(f"Invalid outbound message source {source!r}.")
    if contact.workspace_id != workspace.pk:
        raise ValueError("The contact belongs to a different workspace.")
    if conversation is not None and (
        conversation.workspace_id != workspace.pk or conversation.contact_id != contact.pk
    ):
        raise ValueError("The conversation does not belong to this contact and workspace.")

    phone_number = _resolve_phone_number(workspace, conversation, phone_number)
    check_phone_number(phone_number)
    current = conversation or (
        Conversation.objects.filter(
            workspace=workspace, contact=contact, phone_number=phone_number
        ).first()
    )
    fields = _message_fields(workspace, content, phone_number)
    if isinstance(content, TemplateContent):
        check_template_policy(content.template, contact)
    else:
        check_session_policy(contact, current)

    if reply_to_wamid:
        fields["payload"]["context"] = {"message_id": reply_to_wamid}

    with transaction.atomic():
        if conversation is None:
            conversation, _ = services.get_or_create_conversation(
                workspace.pk, contact, phone_number
            )
        reply_to = (
            Message.objects.filter(workspace=workspace, wamid=reply_to_wamid).first()
            if reply_to_wamid
            else None
        )
        try:
            with transaction.atomic():
                message = Message.objects.create(
                    workspace=workspace,
                    conversation=conversation,
                    direction=Message.Direction.OUTBOUND,
                    status=Message.Status.QUEUED,
                    source=source,
                    source_ref=source_ref or "",
                    sent_by=sent_by,
                    idempotency_key=idempotency_key,
                    reply_to=reply_to,
                    reply_to_wamid=reply_to_wamid or "",
                    **fields,
                )
        except IntegrityError:
            if idempotency_key is None:
                raise
            existing = _find_by_idempotency_key(workspace, idempotency_key)
            if existing is None:
                raise
            return existing
        now = timezone.now()
        Conversation.objects.filter(pk=conversation.pk).update(last_message_at=now, updated_at=now)
        services.emit_message_recorded(message, conversation)
        if dispatch:
            enqueue([message.pk])
    return message


# --- Policy -------------------------------------------------------------------------------------


def check_phone_number(phone_number: PhoneNumber) -> None:
    if not template_services.is_connected(phone_number.waba):
        raise WhatsAppNotConnected()
    registered = phone_number.registration_status == PhoneNumber.RegistrationStatus.REGISTERED
    # Coexistence numbers (shared with the WhatsApp Business app) are never registered.
    if not (registered or phone_number.is_coexistence):
        raise PhoneNumberNotRegistered()


def check_template_policy(template: MessageTemplate | None, contact: Contact) -> None:
    if template is None or template.status != MessageTemplate.Status.APPROVED:
        raise TemplateNotApproved()
    if contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_OUT:
        raise ContactOptedOut()
    if (
        template.category == MessageTemplate.Category.MARKETING
        and contact.marketing_opt_in_status != Contact.OptInStatus.OPTED_IN
    ):
        raise MarketingOptInRequired()


def check_session_policy(contact: Contact, conversation: Conversation | None) -> None:
    """Free-form (non-template) messages: consent first, then the service window."""
    if contact.marketing_opt_in_status == Contact.OptInStatus.OPTED_OUT and not _reengaged(
        contact, conversation
    ):
        raise ContactOptedOut()
    expires = conversation.service_window_expires_at if conversation else None
    if expires is None or expires <= timezone.now():
        raise OutsideServiceWindow()


def check_dispatch_policy(message: Message) -> None:
    """Re-run the checks for a stored message just before it is sent (state may have changed)."""
    conversation = message.conversation
    check_phone_number(conversation.phone_number)
    if message.type == Message.Type.TEMPLATE:
        check_template_policy(message.template, conversation.contact)
    else:
        check_session_policy(conversation.contact, conversation)


def _reengaged(contact: Contact, conversation: Conversation | None) -> bool:
    """The customer wrote to this number after opting out."""
    if conversation is None or conversation.last_inbound_at is None:
        return False
    return contact.opted_out_at is None or conversation.last_inbound_at > contact.opted_out_at


# --- Helpers ------------------------------------------------------------------------------------


def _find_by_idempotency_key(workspace, key: str) -> Message | None:
    return Message.objects.filter(workspace=workspace, idempotency_key=key).first()


def _resolve_phone_number(
    workspace, conversation: Conversation | None, phone_number: PhoneNumber | None
) -> PhoneNumber:
    if phone_number is not None:
        if phone_number.workspace_id != workspace.pk:
            raise ValueError("The phone number belongs to a different workspace.")
        if conversation is not None and conversation.phone_number_id != phone_number.pk:
            raise ValueError("The conversation uses a different phone number.")
        return phone_number
    if conversation is not None:
        return conversation.phone_number
    default = (
        PhoneNumber.objects.select_related("waba")
        .filter(workspace=workspace, is_default=True)
        .first()
    )
    if default is None:
        raise WhatsAppNotConnected("Connect a WhatsApp number and set a default number first.")
    return default


def _message_fields(workspace, content: Content, phone_number: PhoneNumber) -> dict[str, Any]:
    if isinstance(content, TextContent):
        return _text_fields(content)
    if isinstance(content, TemplateContent):
        return _template_fields(workspace, content, phone_number)
    if isinstance(content, MediaContent):
        return _media_fields(workspace, content)
    if isinstance(content, InteractiveContent):
        return _interactive_fields(content)
    raise TypeError(f"Unsupported message content {type(content).__name__}.")


def _interactive_fields(content: InteractiveContent) -> dict[str, Any]:
    from .interactive import InvalidInteractiveContent

    interactive = content.interactive
    if not isinstance(interactive, Mapping) or not interactive.get("type"):
        raise InvalidInteractiveContent("The interactive object needs a type.")
    summary = (content.summary or "").strip()
    if not summary:
        raise InvalidInteractiveContent("An interactive message needs a summary for the inbox.")
    return {
        "type": Message.Type.INTERACTIVE,
        "text": summary[:MAX_TEXT_LENGTH],
        "payload": {"type": "interactive", "interactive": _plain(interactive)},
    }


def _plain(value: Any) -> Any:
    """A JSON-ready deep copy (mappings and sequences become dicts and lists)."""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _text_fields(content: TextContent) -> dict[str, Any]:
    body = content.body or ""
    if not body.strip():
        raise ValidationError({"text": ["This field may not be blank."]})
    if len(body) > MAX_TEXT_LENGTH:
        raise ValidationError(
            {"text": [f"Ensure this field has no more than {MAX_TEXT_LENGTH} characters."]}
        )
    return {
        "type": Message.Type.TEXT,
        "text": body,
        "payload": {"type": "text", "text": {"body": body, "preview_url": content.preview_url}},
    }


def _template_fields(
    workspace, content: TemplateContent, phone_number: PhoneNumber
) -> dict[str, Any]:
    template = content.template
    if template.workspace_id != workspace.pk or template.waba_id != phone_number.waba_id:
        raise ValidationError(
            {"template_id": ["The template belongs to a different WhatsApp Business Account."]}
        )
    if template.status != MessageTemplate.Status.APPROVED:
        raise TemplateNotApproved()
    body_params = [str(value) for value in content.body_params]
    template_object = template_services.build_send_components(
        template,
        body_params=body_params,
        header_param=content.header_param,
        button_params=content.button_params,
    )
    header_variables = [content.header_param] if isinstance(content.header_param, str) else []
    try:
        text = template_services.render_preview(
            template, body_params, header_variables=header_variables
        )["body"]
    except ValidationError:
        text = ""
    return {
        "type": Message.Type.TEMPLATE,
        "text": text,
        "payload": {"type": "template", "template": template_object},
        "template": template,
        "template_name": template.name,
        "template_language": template.language,
        "template_category": template.category,
        "template_components": template_object["components"],
    }


def media_type_for(mime_type: str) -> str:
    mime_type = (mime_type or "").lower()
    if mime_type == "image/webp":
        return Message.Type.STICKER
    for prefix, message_type in (
        ("image/", Message.Type.IMAGE),
        ("video/", Message.Type.VIDEO),
        ("audio/", Message.Type.AUDIO),
    ):
        if mime_type.startswith(prefix):
            return message_type
    return Message.Type.DOCUMENT


def _media_fields(workspace, content: MediaContent) -> dict[str, Any]:
    asset = content.asset
    if asset.workspace_id != workspace.pk:
        raise ValidationError({"media_id": ["The media file belongs to a different workspace."]})
    message_type = media_type_for(asset.mime_type)
    caption = content.caption or ""
    media: dict[str, Any] = {}
    if caption:
        if message_type in (Message.Type.AUDIO, Message.Type.STICKER):
            raise ValidationError({"caption": [f"A {message_type} message cannot have a caption."]})
        if len(caption) > MAX_CAPTION_LENGTH:
            raise ValidationError(
                {
                    "caption": [
                        f"Ensure this field has no more than {MAX_CAPTION_LENGTH} characters."
                    ]
                }
            )
        media["caption"] = caption
    if message_type == Message.Type.DOCUMENT and asset.file_name:
        media["filename"] = asset.file_name
    return {
        "type": message_type,
        "text": caption,
        # The Meta media id is added at dispatch, after uploading to the sending number.
        "payload": {"type": message_type, message_type: media},
        "media_asset": asset,
        "mime_type": asset.mime_type,
        "file_name": asset.file_name,
        "size": asset.size,
        "file": asset.file.name if asset.file else "",
    }
