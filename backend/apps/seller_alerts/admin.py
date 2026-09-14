from django.contrib import admin

from .models import AlertMessage, AlertRecipient, PendingSellerReply


@admin.register(AlertRecipient)
class AlertRecipientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_e164", "workspace", "status", "verified_at", "last_sent_at")
    list_filter = ("status",)
    search_fields = ("name", "phone_e164", "workspace__name")
    raw_id_fields = ("workspace",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(AlertMessage)
class AlertMessageAdmin(admin.ModelAdmin):
    list_display = ("kind", "to_wa_id", "workspace", "status", "error_code", "created_at")
    list_filter = ("kind", "status")
    search_fields = ("wamid", "to_wa_id")
    raw_id_fields = ("recipient", "workspace", "order")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(PendingSellerReply)
class PendingSellerReplyAdmin(admin.ModelAdmin):
    list_display = ("recipient", "order", "action", "expires_at")
    list_filter = ("action",)
    raw_id_fields = ("workspace", "recipient", "order")
    readonly_fields = ("id", "created_at", "updated_at")
