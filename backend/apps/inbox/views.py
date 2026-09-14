"""Inbox API (docs/contracts/wave-2.md): conversations, messages, notes, media and WS tickets.

Writes go through ``apps.inbox.services`` and ``apps.inbox.sending``; realtime frames are sent
from there and from ``receivers.py``.
"""

import contextlib
import mimetypes
import re
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.contacts.models import Contact
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.models import PhoneNumber
from common.phone import InvalidPhoneNumber, normalize_e164
from common.roles import Role
from common.tenancy import WorkspaceScopedAPIView, WorkspaceScopedGenericViewSet
from common.ws_auth import WS_PATH, issue_ticket

from . import media, selectors, sending, services
from .models import Conversation, MediaAsset, Message
from .schema_enums import CONVERSATION_STATUSES
from .serializers import (
    AssignConversationSerializer,
    ConversationNoteSerializer,
    ConversationSerializer,
    MediaAssetSerializer,
    MediaUploadSerializer,
    MessageSerializer,
    SendMessageSerializer,
    StartConversationSerializer,
    WsTicketSerializer,
)

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_KEY_PREFIX = "inbox:"
MAX_IDEMPOTENCY_KEY_LENGTH = 200
_IDEMPOTENCY_KEY_RE = re.compile(r"[\x21-\x7e]+")  # printable ASCII without spaces

IDEMPOTENCY_KEY_PARAMETER = OpenApiParameter(
    name=IDEMPOTENCY_KEY_HEADER,
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Retrying with the same key returns the original message instead of resending.",
)

CONVERSATION_FILTERS = [
    OpenApiParameter("status", OpenApiTypes.STR, enum=CONVERSATION_STATUSES),
    OpenApiParameter(
        "assignee", OpenApiTypes.STR, description="A member's user id, `me` or `none`."
    ),
    OpenApiParameter("phone_number", OpenApiTypes.UUID, description="Business phone number id."),
    OpenApiParameter("unread", OpenApiTypes.BOOL, description="Only conversations with unread."),
    OpenApiParameter("search", OpenApiTypes.STR, description="Contact name or phone number."),
]

_TRUE_VALUES = {"true", "1", "yes"}
_FALSE_VALUES = {"false", "0", "no"}
_MIN_SEARCH_DIGITS = 3
_MAX_SEARCH_LENGTH = 100


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


def _uuid_param(field: str, raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise _invalid(field, "Must be a valid UUID.") from None


class ConversationViewSet(WorkspaceScopedGenericViewSet):
    """Conversations with contacts, newest activity first."""

    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    pagination_class = selectors.ConversationPagination
    filter_backends: list = []
    lookup_value_converter = "uuid"
    read_role = Role.VIEWER
    write_role = Role.AGENT

    # --- helpers --------------------------------------------------------------------------------

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in ("list", "retrieve"):
            return selectors.with_api_fields(queryset)
        return queryset.select_related("contact", "phone_number__waba")

    def validated(self, serializer_class, **kwargs) -> dict:
        serializer = serializer_class(
            data=self.request.data, context=self.get_serializer_context(), **kwargs
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def conversation_response(self, conversation_id, status_code=status.HTTP_200_OK) -> Response:
        conversation = selectors.with_api_fields(
            Conversation.objects.filter(workspace=self.workspace)
        ).get(pk=conversation_id)
        return Response(self.get_serializer(conversation).data, status=status_code)

    def filter_conversations(self, queryset):
        params = self.request.query_params
        if value := params.get("status"):
            if value not in CONVERSATION_STATUSES:
                raise _invalid("status", f"Use one of: {', '.join(CONVERSATION_STATUSES)}.")
            queryset = queryset.filter(status=value)
        if value := params.get("assignee"):
            if value == "me":
                queryset = queryset.filter(assignee=self.request.user)
            elif value == "none":
                queryset = queryset.filter(assignee__isnull=True)
            else:
                queryset = queryset.filter(assignee_id=_uuid_param("assignee", value))
        if value := params.get("phone_number"):
            queryset = queryset.filter(phone_number_id=_uuid_param("phone_number", value))
        if value := params.get("unread"):
            lowered = value.lower()
            if lowered in _TRUE_VALUES:
                queryset = queryset.filter(unread_count__gt=0)
            elif lowered in _FALSE_VALUES:
                queryset = queryset.filter(unread_count=0)
            else:
                raise _invalid("unread", "Must be true or false.")
        if value := params.get("search", "").strip()[:_MAX_SEARCH_LENGTH]:
            queryset = queryset.filter(self.search_filter(value))
        return queryset

    @staticmethod
    def search_filter(value: str) -> Q:
        condition = Q(contact__name__icontains=value)
        with contextlib.suppress(InvalidPhoneNumber):
            condition |= Q(contact__phone_e164=normalize_e164(value))
        digits = re.sub(r"\D", "", value)
        if len(digits) >= _MIN_SEARCH_DIGITS and re.fullmatch(r"[\d\s()+.\-]+", value):
            condition |= Q(contact__phone_e164__contains=digits)
        return condition

    # --- endpoints ------------------------------------------------------------------------------

    @extend_schema(
        operation_id="inbox_conversations_list",
        parameters=CONVERSATION_FILTERS,
        responses=ConversationSerializer(many=True),
    )
    def list(self, request):
        queryset = self.filter_conversations(self.get_queryset())
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(
        operation_id="inbox_conversations_create",
        request=StartConversationSerializer,
        responses={200: ConversationSerializer, 201: ConversationSerializer},
        description="Get or create the conversation with a contact (201 when created).",
    )
    def create(self, request):
        data = self.validated(StartConversationSerializer)
        workspace = self.workspace
        contact = Contact.objects.filter(workspace=workspace, pk=data["contact_id"]).first()
        if contact is None:
            raise _invalid("contact_id", "Contact not found.")
        if data.get("phone_number_id"):
            phone_number = PhoneNumber.objects.filter(
                workspace=workspace, pk=data["phone_number_id"]
            ).first()
            if phone_number is None:
                raise _invalid("phone_number_id", "Phone number not found.")
        else:
            phone_number = PhoneNumber.objects.filter(workspace=workspace, is_default=True).first()
            if phone_number is None:
                raise sending.WhatsAppNotConnected(
                    "Connect a WhatsApp number and set a default number first."
                )
        conversation, created = services.get_or_create_conversation(
            workspace.pk, contact, phone_number
        )
        if created:
            services.notify_conversation_updated(conversation)
        return self.conversation_response(
            conversation.pk, status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @extend_schema(operation_id="inbox_conversations_retrieve", responses=ConversationSerializer)
    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(
        operation_id="inbox_conversations_assign_create",
        request=AssignConversationSerializer,
        responses=ConversationSerializer,
    )
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        conversation = self.get_object()
        data = self.validated(AssignConversationSerializer)
        assignee = None
        if data["assignee_id"] is not None:
            assignee = get_user_model().objects.filter(pk=data["assignee_id"]).first()
            if assignee is None:
                raise _invalid("assignee_id", "The assignee must be a member of this workspace.")
        services.assign(conversation, assignee, actor=request.user)
        return self.conversation_response(conversation.pk)

    @extend_schema(
        operation_id="inbox_conversations_close_create",
        request=None,
        responses=ConversationSerializer,
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        conversation = self.get_object()
        services.close(conversation, actor=request.user)
        return self.conversation_response(conversation.pk)

    @extend_schema(
        operation_id="inbox_conversations_reopen_create",
        request=None,
        responses=ConversationSerializer,
    )
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        conversation = self.get_object()
        services.reopen(conversation, actor=request.user)
        return self.conversation_response(conversation.pk)

    @extend_schema(
        operation_id="inbox_conversations_read_create",
        request=None,
        responses=ConversationSerializer,
        description="Reset the unread count and send a read receipt for the latest inbound.",
    )
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        conversation = self.get_object()
        services.mark_read(conversation, actor=request.user)
        return self.conversation_response(conversation.pk)

    @extend_schema(
        methods=["GET"],
        operation_id="inbox_conversations_messages_list",
        responses=MessageSerializer(many=True),
        description="Messages in the conversation, newest first.",
    )
    @extend_schema(
        methods=["POST"],
        operation_id="inbox_conversations_messages_create",
        request=SendMessageSerializer,
        parameters=[IDEMPOTENCY_KEY_PARAMETER],
        responses={201: MessageSerializer},
        description="Queue a message. Outside the service window only approved templates send.",
    )
    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        context = self.get_serializer_context()
        if request.method != "POST":
            paginator = selectors.MessagePagination()
            page = paginator.paginate_queryset(
                selectors.messages_for(conversation), request, view=self
            )
            data = MessageSerializer(page, many=True, context=context).data
            return paginator.get_paginated_response(data)

        data = self.validated(SendMessageSerializer)
        idempotency_key = self.idempotency_key()
        existing = (
            Message.objects.filter(workspace=self.workspace, idempotency_key=idempotency_key)
            .select_related("sent_by")
            .first()
            if idempotency_key
            else None
        )
        if existing is not None:
            return Response(
                MessageSerializer(existing, context=context).data, status=status.HTTP_201_CREATED
            )
        message = sending.send_message(
            workspace=self.workspace,
            contact=conversation.contact,
            conversation=conversation,
            content=self.message_content(data),
            reply_to_wamid=self.reply_to_wamid(conversation, data.get("reply_to_message_id")),
            source=Message.Source.INBOX,
            sent_by=request.user,
            idempotency_key=idempotency_key,
        )
        return Response(
            MessageSerializer(message, context=context).data, status=status.HTTP_201_CREATED
        )

    def idempotency_key(self) -> str | None:
        raw = self.request.headers.get(IDEMPOTENCY_KEY_HEADER, "").strip()
        if not raw:
            return None
        if len(raw) > MAX_IDEMPOTENCY_KEY_LENGTH or not _IDEMPOTENCY_KEY_RE.fullmatch(raw):
            raise _invalid(
                "idempotency_key",
                f"The {IDEMPOTENCY_KEY_HEADER} header must be at most "
                f"{MAX_IDEMPOTENCY_KEY_LENGTH} printable characters without spaces.",
            )
        return f"{IDEMPOTENCY_KEY_PREFIX}{raw}"

    def message_content(self, data: dict) -> sending.Content:
        workspace = self.workspace
        if data["type"] == "text":
            return sending.TextContent(data["text"], preview_url=data["preview_url"])
        if data["type"] == "template":
            template = MessageTemplate.objects.filter(
                workspace=workspace, pk=data["template_id"]
            ).first()
            if template is None:
                raise _invalid("template_id", "Template not found.")
            return sending.TemplateContent(
                template,
                body_params=tuple(data.get("body_params") or ()),
                header_param=data.get("header_param"),
                button_params={int(key): value for key, value in data["button_params"].items()}
                or None,
            )
        asset = MediaAsset.objects.filter(workspace=workspace, pk=data["media_id"]).first()
        if asset is None:
            raise _invalid("media_id", "Media file not found. Upload it with POST media/ first.")
        return sending.MediaContent(asset, caption=data.get("caption") or "")

    def reply_to_wamid(self, conversation: Conversation, message_id) -> str | None:
        if message_id is None:
            return None
        wamid = (
            Message.objects.filter(
                workspace=self.workspace, conversation=conversation, pk=message_id
            )
            .values_list("wamid", flat=True)
            .first()
        )
        if not wamid:
            raise _invalid(
                "reply_to_message_id",
                "Reply to a message in this conversation that WhatsApp has accepted.",
            )
        return wamid

    @extend_schema(
        methods=["GET"],
        operation_id="inbox_conversations_notes_list",
        responses=ConversationNoteSerializer(many=True),
    )
    @extend_schema(
        methods=["POST"],
        operation_id="inbox_conversations_notes_create",
        request=ConversationNoteSerializer,
        responses={201: ConversationNoteSerializer},
    )
    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        conversation = self.get_object()
        context = self.get_serializer_context()
        if request.method != "POST":
            paginator = selectors.NotePagination()
            page = paginator.paginate_queryset(
                selectors.notes_for(conversation), request, view=self
            )
            data = ConversationNoteSerializer(page, many=True, context=context).data
            return paginator.get_paginated_response(data)

        data = self.validated(ConversationNoteSerializer)
        note = services.add_note(conversation, data["body"], author=request.user)
        return Response(
            ConversationNoteSerializer(note, context=context).data, status=status.HTTP_201_CREATED
        )


class MediaAssetViewSet(WorkspaceScopedGenericViewSet):
    """Uploaded media for outgoing messages."""

    queryset = MediaAsset.objects.all()
    serializer_class = MediaAssetSerializer
    parser_classes = (MultiPartParser, FormParser)
    filter_backends: list = []
    write_role = Role.AGENT

    @extend_schema(
        operation_id="inbox_media_create",
        request={"multipart/form-data": MediaUploadSerializer},
        responses={201: MediaAssetSerializer},
    )
    def create(self, request):
        serializer = MediaUploadSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        mime_type = upload.content_type
        asset = MediaAsset(
            workspace=self.workspace,
            mime_type=mime_type,
            file_name=media.safe_file_name(upload.name),
            size=upload.size,
            uploaded_by=request.user,
        )
        extension = mimetypes.guess_extension(mime_type) or ""
        # Stored under a random name: the original name is only kept for display.
        asset.file.save(f"{uuid.uuid4().hex}{extension}", upload, save=False)
        try:
            with transaction.atomic():
                asset.save()
        except Exception:
            asset.file.storage.delete(asset.file.name)
            raise
        return Response(MediaAssetSerializer(asset).data, status=status.HTTP_201_CREATED)


# Types a browser may render inline; everything else downloads as an attachment.
INLINE_MEDIA_PREFIXES = ("image/", "video/", "audio/")
_MIME_TYPE_RE = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*")


class MessageViewSet(WorkspaceScopedGenericViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    filter_backends: list = []
    lookup_value_converter = "uuid"
    read_role = Role.VIEWER

    @extend_schema(
        operation_id="inbox_messages_media_retrieve",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
        description="Stream the message's stored media file.",
    )
    @action(detail=True, methods=["get"])
    def media(self, request, pk=None):
        message = self.get_object()
        if not message.file:
            raise exceptions.NotFound("This message has no stored media file.")
        try:
            handle = message.file.open("rb")
        except OSError:
            raise exceptions.NotFound("This message has no stored media file.") from None

        content_type = media.base_mime_type(message.mime_type)
        if not _MIME_TYPE_RE.fullmatch(content_type) or content_type == "image/svg+xml":
            content_type = "application/octet-stream"
        extension = mimetypes.guess_extension(content_type) or ""
        default_name = f"{message.type}-{message.pk.hex[:8]}{extension}"
        response = FileResponse(
            handle,
            content_type=content_type,
            as_attachment=not content_type.startswith(INLINE_MEDIA_PREFIXES),
            filename=media.safe_file_name(message.file_name, default=default_name),
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cache-Control"] = "private, no-cache"
        return response


class WsTicketView(WorkspaceScopedAPIView):
    """Issue a single-use ticket for opening the realtime WebSocket (any member)."""

    serializer_class = WsTicketSerializer
    write_role = Role.VIEWER

    @extend_schema(
        operation_id="inbox_ws_ticket_create", request=None, responses=WsTicketSerializer
    )
    def post(self, request):
        membership = self.membership
        ticket = issue_ticket(request.user.pk, membership.workspace_id)
        body = WsTicketSerializer(
            {"ticket": ticket, "expires_in": settings.WS_TICKET_TTL, "path": WS_PATH}
        ).data
        return Response(body, headers={"Cache-Control": "no-store"})
