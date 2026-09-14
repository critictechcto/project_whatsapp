import json

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html

from .models import WebhookEvent
from .tasks import enqueue_on_commit


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "object_type",
        "status",
        "attempts",
        "workspace",
        "processed_at",
    )
    list_filter = ("status", "object_type")
    search_fields = ("body_sha256", "workspace__name")
    list_select_related = ("workspace",)
    date_hierarchy = "created_at"
    actions = ("reprocess_selected",)
    fields = (
        "id",
        "object_type",
        "status",
        "attempts",
        "workspace",
        "last_error",
        "processed_at",
        "body_sha256",
        "created_at",
        "updated_at",
        "formatted_payload",
    )
    readonly_fields = fields

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    @admin.display(description="Payload")
    def formatted_payload(self, obj: WebhookEvent) -> str:
        return format_html(
            '<pre style="white-space: pre-wrap">{}</pre>', json.dumps(obj.payload, indent=2)
        )

    def has_reprocess_permission(self, request) -> bool:
        return request.user.has_perm("webhooks.change_webhookevent")

    @admin.action(description="Reprocess selected", permissions=("reprocess",))
    def reprocess_selected(self, request, queryset) -> None:
        selected = list(queryset.values_list("pk", flat=True))
        with transaction.atomic():
            pks = list(
                WebhookEvent.objects.filter(pk__in=selected)
                .exclude(status=WebhookEvent.Status.PROCESSING)
                .select_for_update()
                .values_list("pk", flat=True)
            )
            WebhookEvent.objects.filter(pk__in=pks).update(
                status=WebhookEvent.Status.RECEIVED, updated_at=timezone.now()
            )
            for pk in pks:
                enqueue_on_commit(pk)
        skipped = len(selected) - len(pks)
        self.message_user(request, f"Queued {len(pks)} webhook event(s) for reprocessing.")
        if skipped:
            self.message_user(
                request, f"Skipped {skipped} event(s) still processing.", messages.WARNING
            )
