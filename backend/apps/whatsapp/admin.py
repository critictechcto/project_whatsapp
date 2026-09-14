from django.contrib import admin

from .models import PhoneNumber, WhatsAppBusinessAccount


class PhoneNumberInline(admin.TabularInline):
    model = PhoneNumber
    extra = 0
    fields = ("phone_number_id", "display_phone_number", "quality_rating", "registration_status")
    readonly_fields = fields
    show_change_link = True


@admin.register(WhatsAppBusinessAccount)
class WhatsAppBusinessAccountAdmin(admin.ModelAdmin):
    list_display = ("waba_id", "name", "workspace", "status", "onboarding_status", "created_at")
    list_filter = ("status", "onboarding_status")
    search_fields = ("waba_id", "name", "workspace__name")
    exclude = ("access_token",)
    readonly_fields = ("id", "created_at", "updated_at", "subscribed_at")
    inlines = (PhoneNumberInline,)


@admin.register(PhoneNumber)
class PhoneNumberAdmin(admin.ModelAdmin):
    list_display = (
        "display_phone_number",
        "verified_name",
        "workspace",
        "quality_rating",
        "messaging_limit_tier",
        "registration_status",
    )
    list_filter = ("quality_rating", "registration_status", "is_coexistence")
    search_fields = ("display_phone_number", "phone_number_id", "verified_name")
    exclude = ("pin",)
    readonly_fields = ("id", "created_at", "updated_at", "last_synced_at")
