from django.contrib import admin

from .models import Invitation, Membership, Workspace


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (MembershipInline,)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "workspace", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("user__email", "workspace__name")
    autocomplete_fields = ("user", "workspace")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "workspace", "role", "expires_at", "accepted_at", "revoked_at")
    search_fields = ("email", "workspace__name")
    exclude = ("token_hash",)
    readonly_fields = ("accepted_at", "accepted_by", "invited_by")
