from django.contrib import admin

from .models import ConsentEvent, Contact, ContactImport, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "workspace", "created_at")
    search_fields = ("name", "workspace__name")
    readonly_fields = ("id", "created_at", "updated_at")


class ConsentEventInline(admin.TabularInline):
    model = ConsentEvent
    extra = 0
    can_delete = False
    fields = ("occurred_at", "action", "source", "evidence", "actor", "wamid")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        "phone_e164",
        "name",
        "workspace",
        "marketing_opt_in_status",
        "last_inbound_at",
        "created_at",
    )
    list_filter = ("marketing_opt_in_status", "opt_in_source")
    search_fields = ("phone_e164", "wa_id", "name", "email", "workspace__name")
    filter_horizontal = ("tags",)
    # Consent changes must go through services so they are audited.
    readonly_fields = (
        "id",
        "marketing_opt_in_status",
        "opted_in_at",
        "opted_out_at",
        "opt_in_source",
        "last_inbound_at",
        "created_at",
        "updated_at",
    )
    inlines = (ConsentEventInline,)


@admin.register(ConsentEvent)
class ConsentEventAdmin(admin.ModelAdmin):
    list_display = ("contact", "action", "source", "workspace", "occurred_at")
    list_filter = ("action", "source", "purpose")
    search_fields = ("contact__phone_e164", "wamid", "workspace__name")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ContactImport)
class ContactImportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "workspace",
        "status",
        "total_rows",
        "created_count",
        "updated_count",
        "error_count",
        "created_at",
    )
    list_filter = ("status", "mark_opted_in")
    search_fields = ("workspace__name",)
    readonly_fields = (
        "id",
        "status",
        "total_rows",
        "created_count",
        "updated_count",
        "skipped_count",
        "error_count",
        "errors",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    )
