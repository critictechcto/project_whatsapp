from django.contrib import admin

from .models import CatalogSyncBatch, Collection, MetaCatalog, MetaCatalogPhoneSetting, Product


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "position", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "workspace__name")
    raw_id_fields = ("workspace",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "name",
        "workspace",
        "price_paise",
        "sale_price_paise",
        "stock_qty",
        "is_active",
        "meta_sync_status",
        "meta_review_status",
    )
    list_filter = ("is_active", "availability", "meta_sync_status", "meta_review_status")
    search_fields = ("sku", "name", "workspace__name")
    raw_id_fields = ("workspace", "collection")
    readonly_fields = ("id", "created_at", "updated_at", "meta_synced_at")


class MetaCatalogPhoneSettingInline(admin.TabularInline):
    model = MetaCatalogPhoneSetting
    extra = 0
    raw_id_fields = ("workspace", "phone_number")


@admin.register(MetaCatalog)
class MetaCatalogAdmin(admin.ModelAdmin):
    list_display = ("catalog_name", "catalog_id", "workspace", "waba", "status", "last_synced_at")
    list_filter = ("status",)
    search_fields = ("catalog_id", "catalog_name", "workspace__name")
    raw_id_fields = ("workspace", "waba", "connected_by")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (MetaCatalogPhoneSettingInline,)


@admin.register(CatalogSyncBatch)
class CatalogSyncBatchAdmin(admin.ModelAdmin):
    list_display = ("handle", "meta_catalog", "status", "created_at", "finished_at")
    list_filter = ("status",)
    search_fields = ("handle",)
    raw_id_fields = ("workspace", "meta_catalog")
    readonly_fields = ("id", "created_at", "updated_at")
