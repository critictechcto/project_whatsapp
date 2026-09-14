from django.contrib import admin

from .models import Order, OrderCounter, OrderEvent, OrderItem, ShopperAddress, StoreSettings


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ("workspace", "store_name", "enabled", "shop_mode", "order_prefix")
    list_filter = ("enabled", "shop_mode")
    search_fields = ("store_name", "workspace__name")
    raw_id_fields = (
        "workspace",
        "phone_number",
        "confirmed_template",
        "packed_template",
        "shipped_template",
        "delivered_template",
        "cancelled_template",
        "payment_reminder_template",
    )
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(OrderCounter)
class OrderCounterAdmin(admin.ModelAdmin):
    list_display = ("workspace", "last_value", "updated_at")
    raw_id_fields = ("workspace",)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ("workspace", "product")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "workspace",
        "status",
        "payment_status",
        "payment_method",
        "total_paise",
        "created_at",
    )
    list_filter = ("status", "payment_status", "payment_method", "source")
    search_fields = ("number", "contact__phone_e164", "contact__name", "workspace__name")
    raw_id_fields = ("workspace", "contact", "conversation", "phone_number")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (OrderItemInline,)


@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = ("order", "type", "from_status", "to_status", "actor", "created_at")
    list_filter = ("type", "actor")
    search_fields = ("order__number",)
    raw_id_fields = ("workspace", "order", "user", "message")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ShopperAddress)
class ShopperAddressAdmin(admin.ModelAdmin):
    list_display = ("contact", "workspace", "last_used_at")
    raw_id_fields = ("workspace", "contact")
    readonly_fields = ("id", "created_at", "updated_at")
