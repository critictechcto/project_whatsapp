from django.contrib import admin

from .models import Campaign, CampaignRecipient


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "status", "scheduled_at", "total_count", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "workspace__name")
    raw_id_fields = ("workspace", "template", "phone_number", "attested_by", "created_by")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(CampaignRecipient)
class CampaignRecipientAdmin(admin.ModelAdmin):
    list_display = ("id", "campaign", "contact", "status", "skip_reason", "error_code")
    list_filter = ("status", "skip_reason")
    search_fields = ("contact__phone_e164", "campaign__name")
    raw_id_fields = ("workspace", "campaign", "contact", "message")
    readonly_fields = ("id", "created_at", "updated_at")
