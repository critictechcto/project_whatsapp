from django.contrib import admin

from .models import Conversation, ConversationNote, MediaAsset, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "contact",
        "phone_number",
        "workspace",
        "status",
        "unread_count",
        "last_message_at",
    )
    list_filter = ("status",)
    search_fields = ("contact__phone_e164", "contact__name", "workspace__name")
    raw_id_fields = ("workspace", "contact", "phone_number", "assignee")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "direction", "type", "status", "source", "created_at")
    list_filter = ("direction", "status", "source", "type")
    search_fields = ("wamid", "source_ref", "idempotency_key")
    raw_id_fields = (
        "workspace",
        "conversation",
        "template",
        "sent_by",
        "reply_to",
        "media_asset",
    )
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("file_name", "mime_type", "size", "workspace", "created_at")
    search_fields = ("file_name", "workspace__name")
    raw_id_fields = ("workspace", "uploaded_by")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ConversationNote)
class ConversationNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "author", "created_at")
    raw_id_fields = ("workspace", "conversation", "author")
    readonly_fields = ("id", "created_at", "updated_at")
