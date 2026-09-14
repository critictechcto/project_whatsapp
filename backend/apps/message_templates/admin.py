from django.contrib import admin

from .models import MessageTemplate


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "language",
        "category",
        "status",
        "quality_score",
        "waba",
        "workspace",
        "updated_at",
    )
    list_filter = ("status", "category", "quality_score", "waba")
    search_fields = ("name", "meta_template_id", "workspace__name")
    readonly_fields = (
        "id",
        "meta_template_id",
        "submitted_at",
        "last_synced_at",
        "created_by",
        "created_at",
        "updated_at",
    )
    list_select_related = ("waba", "workspace")
