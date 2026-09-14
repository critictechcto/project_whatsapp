"""Inbox API. Endpoint bodies are stubs (501) until the messaging core lands, except ws-ticket.

Roles and request validation are already enforced, so replacing a stub body keeps the contract.
"""

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.roles import Role
from common.tenancy import WorkspaceScopedAPIView, WorkspaceScopedGenericViewSet
from common.ws_auth import WS_PATH, issue_ticket

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


class StubNotImplemented(exceptions.APIException):
    status_code = 501
    default_code = "not_implemented"
    default_detail = "This endpoint is not available yet."


IDEMPOTENCY_KEY_PARAMETER = OpenApiParameter(
    name="Idempotency-Key",
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


class StubViewMixin:
    filter_backends: list = []

    def validated(self, serializer_class, **kwargs) -> dict:
        serializer = serializer_class(
            data=self.request.data, context=self.get_serializer_context(), **kwargs
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class ConversationViewSet(StubViewMixin, WorkspaceScopedGenericViewSet):
    """Conversations with contacts, newest activity first."""

    serializer_class = ConversationSerializer
    lookup_value_converter = "uuid"
    read_role = Role.VIEWER
    write_role = Role.AGENT

    @extend_schema(
        operation_id="inbox_conversations_list",
        parameters=CONVERSATION_FILTERS,
        responses=ConversationSerializer(many=True),
    )
    def list(self, request):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="inbox_conversations_create",
        request=StartConversationSerializer,
        responses={200: ConversationSerializer, 201: ConversationSerializer},
        description="Get or create the conversation with a contact (201 when created).",
    )
    def create(self, request):
        self.validated(StartConversationSerializer)
        raise StubNotImplemented()

    @extend_schema(operation_id="inbox_conversations_retrieve", responses=ConversationSerializer)
    def retrieve(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="inbox_conversations_assign_create",
        request=AssignConversationSerializer,
        responses=ConversationSerializer,
    )
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        self.validated(AssignConversationSerializer)
        raise StubNotImplemented()

    @extend_schema(
        operation_id="inbox_conversations_close_create",
        request=None,
        responses=ConversationSerializer,
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="inbox_conversations_reopen_create",
        request=None,
        responses=ConversationSerializer,
    )
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="inbox_conversations_read_create",
        request=None,
        responses=ConversationSerializer,
        description="Reset the unread count and send a read receipt for the latest inbound.",
    )
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        raise StubNotImplemented()

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
        if request.method == "POST":
            self.validated(SendMessageSerializer)
        raise StubNotImplemented()

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
        if request.method == "POST":
            self.validated(ConversationNoteSerializer)
        raise StubNotImplemented()


class MediaAssetViewSet(StubViewMixin, WorkspaceScopedGenericViewSet):
    """Uploaded media for outgoing messages."""

    serializer_class = MediaAssetSerializer
    parser_classes = (MultiPartParser, FormParser)
    write_role = Role.AGENT

    @extend_schema(
        operation_id="inbox_media_create",
        request={"multipart/form-data": MediaUploadSerializer},
        responses={201: MediaAssetSerializer},
    )
    def create(self, request):
        self.validated(MediaUploadSerializer)
        raise StubNotImplemented()


class MessageViewSet(StubViewMixin, WorkspaceScopedGenericViewSet):
    serializer_class = MessageSerializer
    lookup_value_converter = "uuid"
    read_role = Role.VIEWER

    @extend_schema(
        operation_id="inbox_messages_media_retrieve",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
        description="Stream the message's stored media file.",
    )
    @action(detail=True, methods=["get"])
    def media(self, request, pk=None):
        raise StubNotImplemented()


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
