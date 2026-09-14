from django.contrib import admin

from .models import BotSession


@admin.register(BotSession)
class BotSessionAdmin(admin.ModelAdmin):
    list_display = ("conversation", "workspace", "state", "last_message_at", "expires_at")
    list_filter = ("state",)
    raw_id_fields = ("workspace", "conversation")
    readonly_fields = ("id", "created_at", "updated_at")
