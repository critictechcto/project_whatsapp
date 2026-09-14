from django.contrib import admin

from .models import AutomationRule, AutomationRun, BusinessHours


@admin.register(AutomationRule)
class AutomationRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "trigger", "is_active", "priority", "run_count")
    list_filter = ("trigger", "is_active")
    search_fields = ("name",)
    raw_id_fields = ("workspace", "phone_number")
    readonly_fields = ("run_count", "last_triggered_at", "created_at", "updated_at")


@admin.register(BusinessHours)
class BusinessHoursAdmin(admin.ModelAdmin):
    list_display = ("workspace", "enabled", "updated_at")
    raw_id_fields = ("workspace",)


@admin.register(AutomationRun)
class AutomationRunAdmin(admin.ModelAdmin):
    list_display = ("rule", "workspace", "status", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("workspace", "rule", "conversation", "message")
    readonly_fields = ("action_results", "detail", "created_at", "updated_at")
