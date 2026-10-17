from django.contrib import admin

from .models import OfferClaim, OfferCode


@admin.register(OfferCode)
class OfferCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "workspace", "discount_type", "discount_value", "is_active", "ends_at")
    list_filter = ("discount_type", "applies_to", "is_active")
    search_fields = ("code", "title")
    raw_id_fields = ("workspace",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(OfferClaim)
class OfferClaimAdmin(admin.ModelAdmin):
    list_display = ("offer", "workspace", "contact", "status", "discount_paise", "created_at")
    list_filter = ("status",)
    search_fields = ("offer__code", "contact__phone_e164", "wamid")
    raw_id_fields = (
        "workspace",
        "offer",
        "contact",
        "conversation",
        "message",
        "order",
        "redeemed_by",
    )
    readonly_fields = ("created_at", "updated_at")
