"""Read-side querysets and pagination for the inbox API."""

from django.db.models import OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce, JSONObject, Left

from common.pagination import DefaultCursorPagination

from .models import Conversation, ConversationNote, Message
from .serializers import PREVIEW_TEXT_LENGTH

# Conversations order by latest activity; ones without messages fall back to their creation time.
ACTIVITY_FIELD = "activity_at"


class ConversationPagination(DefaultCursorPagination):
    ordering = (f"-{ACTIVITY_FIELD}", "-id")


class MessagePagination(DefaultCursorPagination):
    ordering = ("-created_at", "-id")


class NotePagination(DefaultCursorPagination):
    ordering = ("-created_at", "-id")


def last_message_preview() -> Subquery:
    """The newest message of the outer conversation as one JSON object (a single index lookup
    per row on ``inbox_msg_conv_created_idx``)."""
    return Subquery(
        Message.objects.filter(conversation_id=OuterRef("pk"))
        .order_by("-created_at", "-id")
        .values(
            preview=JSONObject(
                direction="direction",
                type="type",
                text=Left("text", PREVIEW_TEXT_LENGTH),
                status="status",
                created_at="created_at",
            )
        )[:1]
    )


def with_api_fields(queryset: QuerySet[Conversation]) -> QuerySet[Conversation]:
    """Everything ``ConversationSerializer`` reads, in one query."""
    return queryset.select_related("contact", "phone_number", "assignee").annotate(
        last_message_preview=last_message_preview(),
        **{ACTIVITY_FIELD: Coalesce("last_message_at", "created_at")},
    )


def messages_for(conversation: Conversation) -> QuerySet[Message]:
    return Message.objects.filter(
        workspace_id=conversation.workspace_id, conversation=conversation
    ).select_related("sent_by")


def notes_for(conversation: Conversation) -> QuerySet[ConversationNote]:
    return ConversationNote.objects.filter(
        workspace_id=conversation.workspace_id, conversation=conversation
    ).select_related("author")
