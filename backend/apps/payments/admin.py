from django.contrib import admin

from .models import PaymentAccount, PaymentLink, PaymentWebhookEvent


@admin.register(PaymentAccount)
class PaymentAccountAdmin(admin.ModelAdmin):
    """Secrets and the webhook token are never shown or editable here."""

    list_display = ("workspace", "provider", "key_id", "status", "verified_at")
    list_filter = ("provider", "status")
    search_fields = ("key_id", "workspace__name")
    raw_id_fields = ("workspace",)
    fields = (
        "id",
        "workspace",
        "provider",
        "key_id",
        "status",
        "verified_at",
        "last_error",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("id", "key_id", "created_at", "updated_at")


@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    list_display = ("reference_id", "workspace", "order", "status", "amount_paise", "created_at")
    list_filter = ("status", "provider")
    search_fields = ("reference_id", "provider_link_id", "order__number")
    raw_id_fields = ("workspace", "order")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "workspace", "event_type", "processed_at", "created_at")
    list_filter = ("event_type",)
    search_fields = ("event_id",)
    raw_id_fields = ("workspace",)
    readonly_fields = ("id", "created_at", "updated_at")
