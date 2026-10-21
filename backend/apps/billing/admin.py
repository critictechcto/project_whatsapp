from django.contrib import admin

from .models import (
    BillingOrder,
    BillingProfile,
    Invoice,
    Plan,
    RazorpayEvent,
    Subscription,
    UsageRecord,
)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "monthly_price_paise", "annual_price_paise", "is_active")
    ordering = ("sort_order",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "workspace",
        "plan",
        "status",
        "interval",
        "trial_ends_at",
        "current_period_end",
    )
    list_filter = ("status", "provider", "plan", "interval")
    raw_id_fields = ("workspace",)
    readonly_fields = (
        "razorpay_subscription_id",
        "razorpay_customer_id",
        "activated_at",
        "renewal_reminder_key",
    )


@admin.register(BillingProfile)
class BillingProfileAdmin(admin.ModelAdmin):
    list_display = ("workspace", "legal_name", "gstin", "state_code")
    raw_id_fields = ("workspace",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "workspace", "status", "issued_at", "total_paise")
    list_filter = ("status", "financial_year")
    search_fields = ("number", "payment_id")
    raw_id_fields = ("workspace", "subscription")

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(BillingOrder)
class BillingOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_id",
        "workspace",
        "plan",
        "interval",
        "amount_paise",
        "status",
        "paid_at",
        "created_at",
    )
    list_filter = ("status", "provider", "plan", "interval")
    search_fields = ("order_id", "payment_id")
    raw_id_fields = ("workspace",)
    exclude = ("payment_session_id",)

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(RazorpayEvent)
class RazorpayEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "type", "created_at", "processed_at")
    list_filter = ("type",)

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("workspace", "metric", "amount", "key", "created_at")
    raw_id_fields = ("workspace",)
