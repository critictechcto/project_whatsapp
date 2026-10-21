from django import forms
from django.contrib import admin

from . import prices
from .invoices import format_inr
from .models import (
    BillingOrder,
    BillingProfile,
    Invoice,
    Plan,
    RazorpayEvent,
    RazorpayPlan,
    Subscription,
    UsageRecord,
)
from .razorpay import RazorpayError

PLAN_ID_FIELDS = (("monthly", "razorpay_plan_id_monthly"), ("annual", "razorpay_plan_id_annual"))
NOT_FOUND_MESSAGE = (
    "Razorpay has no plan with this id. Check that it was created in the same mode (test or "
    "live) as RAZORPAY_ENV."
)
UNREACHABLE_MESSAGE = "Razorpay couldn't be reached to check this plan. Try again."


class PlanAdminForm(forms.ModelForm):
    """Prices come from Razorpay: each Razorpay plan id is fetched and checked on save."""

    class Meta:
        model = Plan
        fields = (
            "slug",
            "name",
            "razorpay_plan_id_monthly",
            "razorpay_plan_id_annual",
            "limits",
            "features",
            "is_active",
            "sort_order",
        )

    def clean(self):
        cleaned = super().clean()
        self.razorpay_plans: dict[str, tuple[str, dict]] = {}
        for interval, field in PLAN_ID_FIELDS:
            plan_id = (cleaned.get(field) or "").strip()
            if field in cleaned:
                cleaned[field] = plan_id
            if not plan_id:
                continue
            try:
                fields = prices.check_plan_id(plan_id, interval)
            except prices.RazorpayPlanNotFound:
                self.add_error(field, NOT_FOUND_MESSAGE)
            except prices.PlanPriceNotConfigured as exc:
                self.add_error(field, str(exc))
            except RazorpayError:
                self.add_error(field, UNREACHABLE_MESSAGE)
            else:
                self.razorpay_plans[interval] = (plan_id, fields)
        return cleaned


def _razorpay_plan_summary(plan: Plan, interval: str) -> str:
    if not plan.razorpay_plan_id(interval):
        return "Not set: can't be bought"
    try:
        snapshot = prices.razorpay_plan(plan, interval)
    except prices.PlanPriceNotConfigured as exc:
        return f"Unavailable: {exc}"
    except RazorpayError:
        return "Razorpay unreachable"
    price = prices.base_price_paise(snapshot.amount_paise)
    text = f"{format_inr(snapshot.amount_paise)} charged ({format_inr(price)} before GST)"
    if snapshot.item_name:
        text += f" - {snapshot.item_name}"
    if not plan.configured_razorpay_plan_id(interval):
        text += " [id from RAZORPAY_PLAN_IDS]"
    return text


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    form = PlanAdminForm
    list_display = ("slug", "name", "monthly_razorpay_plan", "annual_razorpay_plan", "is_active")
    ordering = ("sort_order",)
    readonly_fields = ("monthly_razorpay_plan", "annual_razorpay_plan")

    @admin.display(description="Monthly (Razorpay)")
    def monthly_razorpay_plan(self, obj: Plan) -> str:
        return _razorpay_plan_summary(obj, "monthly") if obj and obj.pk else "-"

    @admin.display(description="Annual (Razorpay)")
    def annual_razorpay_plan(self, obj: Plan) -> str:
        return _razorpay_plan_summary(obj, "annual") if obj and obj.pk else "-"

    def save_model(self, request, obj, form, change) -> None:
        super().save_model(request, obj, form, change)
        for interval, (plan_id, fields) in getattr(form, "razorpay_plans", {}).items():
            prices.assign(obj, interval, plan_id, fields)


@admin.register(RazorpayPlan)
class RazorpayPlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "plan",
        "interval",
        "item_name",
        "amount_paise",
        "currency",
        "period",
        "period_interval",
        "fetched_at",
    )
    list_filter = ("plan", "interval")
    search_fields = ("id", "item_name")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


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
