"""The generated schema carries the wave-3 commerce contract names
(docs/contracts/wave-3-commerce.md). Frontend types are generated from them.

PATCH bodies follow drf-spectacular's ``Patched<Name>Request`` naming, as in wave 2.
"""

import pytest
from drf_spectacular.generators import SchemaGenerator

CONTRACT_COMPONENTS = {
    # catalog
    "Product",
    "ProductWriteRequest",
    "PatchedProductWriteRequest",
    "CollectionRef",
    "Collection",
    "CollectionWriteRequest",
    "PatchedCollectionWriteRequest",
    "ReorderRequest",
    "ProductImportResult",
    "ProductImportRowError",
    "MetaCatalog",
    "MetaCatalogWaba",
    "MetaCatalogCounts",
    "CommerceSettings",
    "PatchedCommerceSettingsRequest",
    "AvailableCatalog",
    "MetaCatalogConnectRequest",
    "PaginatedProductList",
    "PaginatedCollectionList",
    "PaginatedMetaCatalogList",
    # orders
    "OrderListItem",
    "Order",
    "OrderItem",
    "OrderAddress",
    "OrderPaymentLink",
    "OrderEvent",
    "OrderTransitionRequest",
    "CancelOrderRequest",
    "PatchedOrderNotesRequest",
    "OrderSummary",
    "PaginatedOrderListItemList",
    "PaginatedOrderEventList",
    # store
    "StoreSettings",
    "PatchedStoreSettingsRequest",
    "OrderNotificationTemplates",
    "StoreChecklist",
    "StoreChecklistItem",
    "StarterTemplatesResult",
    # payments
    "PaymentAccount",
    "PatchedPaymentAccountRequest",
    "PaymentLink",
    "PaginatedPaymentLinkList",
    # seller alerts
    "AlertRecipient",
    "AlertRecipientRequest",
    "PatchedAlertRecipientRequest",
    "PlatformAlertsInfo",
    "PaginatedAlertRecipientList",
}

CONTRACT_ENUMS = {
    "ProductAvailabilityEnum": ["in_stock", "out_of_stock"],
    "CatalogSyncStatusEnum": ["not_synced", "pending", "synced", "failed"],
    "MetaReviewStatusEnum": ["none", "pending", "approved", "rejected", "outdated"],
    "MetaCatalogStatusEnum": ["connected", "permissions_missing", "error"],
    "ShopModeEnum": ["bot", "native_catalog"],
    "OrderStatusEnum": [
        "draft",
        "awaiting_confirmation",
        "awaiting_address",
        "awaiting_payment_method",
        "pending_payment",
        "confirmed",
        "packed",
        "shipped",
        "delivered",
        "cancelled",
        "expired",
        "needs_attention",
    ],
    "PaymentStatusEnum": ["unpaid", "paid", "cod_pending", "cod_collected", "refunded_manual"],
    "PaymentMethodEnum": ["online", "cod"],
    "OrderSourceEnum": ["bot", "native_cart"],
    "OrderEventTypeEnum": [
        "created",
        "status_changed",
        "price_changed",
        "address_received",
        "payment_link_created",
        "payment_received",
        "payment_link_expired",
        "cod_collected",
        "refunded_manual",
        "stock_released",
        "notification_sent",
        "notification_failed",
        "note",
    ],
    "OrderEventActorEnum": ["buyer", "dashboard", "seller_whatsapp", "system"],
    "PaymentProviderEnum": ["razorpay", "cashfree"],
    "PaymentModeEnum": ["test", "live"],
    "PaymentAccountStatusEnum": ["not_configured", "unverified", "verified", "invalid"],
    "PaymentLinkStatusEnum": ["creating", "created", "paid", "expired", "cancelled", "failed"],
    "AlertRecipientStatusEnum": ["pending", "verified", "opted_out"],
    "AlertEventEnum": ["new_order", "needs_attention", "order_cancelled"],
}

CONTRACT_PATHS = {
    "/api/v1/catalog/products/": {"get", "post"},
    "/api/v1/catalog/products/{id}/": {"get", "patch", "delete"},
    "/api/v1/catalog/products/{id}/image/": {"post", "delete"},
    "/api/v1/catalog/products/import/": {"post"},
    "/api/v1/catalog/products/reorder/": {"post"},
    "/api/v1/catalog/collections/": {"get", "post"},
    "/api/v1/catalog/collections/{id}/": {"get", "patch", "delete"},
    "/api/v1/catalog/collections/reorder/": {"post"},
    "/api/v1/catalog/meta-catalogs/": {"get", "post"},
    "/api/v1/catalog/meta-catalogs/available/": {"get"},
    "/api/v1/catalog/meta-catalogs/{id}/": {"get", "delete"},
    "/api/v1/catalog/meta-catalogs/{id}/sync/": {"post"},
    "/api/v1/catalog/meta-catalogs/{id}/commerce-settings/": {"patch"},
    "/api/v1/orders/": {"get"},
    "/api/v1/orders/{id}/": {"get", "patch"},
    "/api/v1/orders/{id}/events/": {"get"},
    "/api/v1/orders/{id}/transition/": {"post"},
    "/api/v1/orders/{id}/cancel/": {"post"},
    "/api/v1/orders/{id}/mark-cod-collected/": {"post"},
    "/api/v1/orders/{id}/mark-refunded/": {"post"},
    "/api/v1/orders/summary/": {"get"},
    "/api/v1/store/settings/": {"get", "patch"},
    "/api/v1/store/checklist/": {"get"},
    "/api/v1/store/starter-templates/": {"post"},
    "/api/v1/payments/account/": {"get", "patch", "delete"},
    "/api/v1/payments/account/verify/": {"post"},
    "/api/v1/payments/account/rotate-webhook/": {"post"},
    "/api/v1/payments/links/": {"get"},
    "/api/v1/seller-alerts/platform/": {"get"},
    "/api/v1/seller-alerts/recipients/": {"get", "post"},
    "/api/v1/seller-alerts/recipients/{id}/": {"patch", "delete"},
    "/api/v1/seller-alerts/recipients/{id}/resend-verification/": {"post"},
}

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def test_contract_components_exist(schema):
    missing = CONTRACT_COMPONENTS - set(schema["components"]["schemas"])
    assert not missing, sorted(missing)


def test_contract_enums_have_contract_values(schema):
    components = schema["components"]["schemas"]
    for name, values in CONTRACT_ENUMS.items():
        assert name in components, name
        assert components[name]["enum"] == values, name


def test_contract_paths_and_methods_exist(schema):
    for path, methods in CONTRACT_PATHS.items():
        assert path in schema["paths"], path
        documented = set(schema["paths"][path]) & HTTP_METHODS
        assert methods <= documented, (path, methods - documented)


def test_secrets_are_write_only(schema):
    account = schema["components"]["schemas"]["PaymentAccount"]["properties"]
    assert "key_secret" not in account
    assert "webhook_secret" not in account
    request = schema["components"]["schemas"]["PatchedPaymentAccountRequest"]["properties"]
    assert {"provider", "mode", "key_id", "key_secret", "webhook_secret"} <= set(request)
