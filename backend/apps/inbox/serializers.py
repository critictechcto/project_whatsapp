"""Inbox API shapes (docs/contracts/wave-2.md). ``FooSerializer`` produces component ``Foo``.

``UserSummarySerializer``, ``ConversationContactSerializer`` and
``ConversationPhoneNumberSerializer`` are shared components: other apps reuse these classes (a
second class with the same component name would be a schema collision).
"""

from django.conf import settings
from rest_framework import serializers

from apps.contacts.models import Contact

from .schema_enums import (
    CONVERSATION_STATUSES,
    MESSAGE_DIRECTIONS,
    MESSAGE_SOURCES,
    MESSAGE_STATUSES,
    MESSAGE_TYPES,
    SEND_MESSAGE_TYPES,
)

MAX_TEXT_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024
MAX_NOTE_LENGTH = 4000

# --- Shared summaries -----------------------------------------------------------------------


class UserSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)


class ConversationContactSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    phone_e164 = serializers.CharField(read_only=True)
    marketing_opt_in_status = serializers.ChoiceField(
        choices=Contact.OptInStatus.choices, read_only=True
    )


class ConversationPhoneNumberSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    display_phone_number = serializers.CharField(read_only=True)
    verified_name = serializers.CharField(read_only=True)


# --- Conversations --------------------------------------------------------------------------


class MessagePreviewSerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=MESSAGE_DIRECTIONS, read_only=True)
    type = serializers.ChoiceField(choices=MESSAGE_TYPES, read_only=True)
    text = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=MESSAGE_STATUSES, read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class ConversationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    contact = ConversationContactSerializer(read_only=True)
    phone_number = ConversationPhoneNumberSerializer(read_only=True)
    status = serializers.ChoiceField(choices=CONVERSATION_STATUSES, read_only=True)
    assignee = UserSummarySerializer(read_only=True, allow_null=True)
    unread_count = serializers.IntegerField(read_only=True)
    last_message_at = serializers.DateTimeField(read_only=True, allow_null=True)
    last_inbound_at = serializers.DateTimeField(read_only=True, allow_null=True)
    service_window_expires_at = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
        help_text="End of the 24-hour customer service window; free-form replies need it open.",
    )
    window_open = serializers.BooleanField(read_only=True)
    last_message = MessagePreviewSerializer(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class StartConversationSerializer(serializers.Serializer):
    contact_id = serializers.UUIDField()
    phone_number_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Business number to use; the workspace default number when omitted.",
    )


class AssignConversationSerializer(serializers.Serializer):
    assignee_id = serializers.UUIDField(
        allow_null=True, help_text="A member's user id, or null to unassign."
    )


class ConversationNoteSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    body = serializers.CharField(max_length=MAX_NOTE_LENGTH)
    author = UserSummarySerializer(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def validate_body(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value


# --- Messages -------------------------------------------------------------------------------


class MessageTemplateRefSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True, allow_null=True)
    name = serializers.CharField(read_only=True)
    language = serializers.CharField(read_only=True)


class MessageMediaSerializer(serializers.Serializer):
    mime_type = serializers.CharField(read_only=True)
    file_name = serializers.CharField(read_only=True)
    size = serializers.IntegerField(read_only=True, help_text="Bytes.")
    download_url = serializers.CharField(read_only=True, allow_null=True)


class MessageSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    conversation_id = serializers.UUIDField(read_only=True)
    direction = serializers.ChoiceField(choices=MESSAGE_DIRECTIONS, read_only=True)
    type = serializers.ChoiceField(choices=MESSAGE_TYPES, read_only=True)
    text = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=MESSAGE_STATUSES, read_only=True)
    source = serializers.ChoiceField(choices=MESSAGE_SOURCES, read_only=True)
    error_code = serializers.CharField(read_only=True, help_text='"" when there is no error.')
    error_message = serializers.CharField(read_only=True)
    template = MessageTemplateRefSerializer(read_only=True, allow_null=True)
    media = MessageMediaSerializer(read_only=True, allow_null=True)
    reply_to_message_id = serializers.UUIDField(read_only=True, allow_null=True)
    sent_by = UserSummarySerializer(read_only=True, allow_null=True)
    wamid = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    sent_at = serializers.DateTimeField(read_only=True, allow_null=True)
    delivered_at = serializers.DateTimeField(read_only=True, allow_null=True)
    read_at = serializers.DateTimeField(read_only=True, allow_null=True)
    failed_at = serializers.DateTimeField(read_only=True, allow_null=True)


class SendMessageSerializer(serializers.Serializer):
    """Body of ``POST conversations/{id}/messages/``; required fields depend on ``type``."""

    type = serializers.ChoiceField(choices=SEND_MESSAGE_TYPES)
    # text
    text = serializers.CharField(required=False, max_length=MAX_TEXT_LENGTH)
    preview_url = serializers.BooleanField(default=False)
    # template
    template_id = serializers.UUIDField(required=False)
    body_params = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False, default=list
    )
    header_param = serializers.CharField(required=False)
    button_params = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        default=dict,
        help_text="Button parameters keyed by button index ('0', '1', ...).",
    )
    # media
    media_id = serializers.UUIDField(required=False, help_text="Id from POST media/.")
    caption = serializers.CharField(required=False, allow_blank=True, max_length=MAX_CAPTION_LENGTH)
    reply_to_message_id = serializers.UUIDField(required=False, allow_null=True)

    REQUIRED_BY_TYPE = {"text": "text", "template": "template_id", "media": "media_id"}

    def validate_button_params(self, value: dict) -> dict:
        if any(not str(key).isdigit() for key in value):
            raise serializers.ValidationError("Keys must be button indexes such as '0'.")
        return value

    def validate(self, attrs: dict) -> dict:
        required = self.REQUIRED_BY_TYPE[attrs["type"]]
        value = attrs.get(required)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise serializers.ValidationError(
                {required: [f"This field is required when type is {attrs['type']}."]}
            )
        return attrs


# --- Media ----------------------------------------------------------------------------------


def media_kind(content_type: str) -> str:
    """Meta media type for an upload's MIME type (decides the size limit)."""
    content_type = (content_type or "").lower()
    if content_type == "image/webp":
        return "sticker"
    for kind in ("image", "video", "audio"):
        if content_type.startswith(f"{kind}/"):
            return kind
    return "document"


class MediaAssetSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    mime_type = serializers.CharField(read_only=True)
    file_name = serializers.CharField(read_only=True)
    size = serializers.IntegerField(read_only=True, help_text="Bytes.")
    created_at = serializers.DateTimeField(read_only=True)


class MediaUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="Within Meta's size limit for the media type.")

    def validate_file(self, value):
        kind = media_kind(getattr(value, "content_type", ""))
        limit = settings.WHATSAPP_MEDIA_MAX_BYTES[kind]
        if value.size > limit:
            raise serializers.ValidationError(
                f"The {kind} is larger than WhatsApp's {limit // 1024} KB limit."
            )
        return value


# --- Realtime -------------------------------------------------------------------------------


class WsTicketSerializer(serializers.Serializer):
    ticket = serializers.CharField(read_only=True, help_text="Single use.")
    expires_in = serializers.IntegerField(read_only=True, help_text="Seconds.")
    path = serializers.CharField(read_only=True, help_text="Connect to <path>?ticket=<ticket>.")
