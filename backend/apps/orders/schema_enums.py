"""Contract enum names for orders and the store (docs/contracts/wave-3-commerce.md). Values only."""

SHOP_MODES = ("bot", "native_catalog")
ORDER_STATUSES = (
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
)
ORDER_STAGES = ("checkout", "open", "closed")
PAYMENT_STATUSES = ("unpaid", "paid", "cod_pending", "cod_collected", "refunded_manual")
PAYMENT_METHODS = ("online", "cod")
ORDER_SOURCES = ("bot", "native_cart")
ORDER_EVENT_TYPES = (
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
)
ORDER_EVENT_ACTORS = ("buyer", "dashboard", "seller_whatsapp", "system")
# OrderTransitionRequest.to_status: the statuses a member may move an order to by hand.
TRANSITION_TARGETS = ("confirmed", "packed", "shipped", "delivered")

ENUM_NAME_OVERRIDES = {
    "ShopModeEnum": SHOP_MODES,
    "OrderStatusEnum": ORDER_STATUSES,
    "OrderStageEnum": ORDER_STAGES,
    "PaymentStatusEnum": PAYMENT_STATUSES,
    "PaymentMethodEnum": PAYMENT_METHODS,
    "OrderSourceEnum": ORDER_SOURCES,
    "OrderEventTypeEnum": ORDER_EVENT_TYPES,
    "OrderEventActorEnum": ORDER_EVENT_ACTORS,
    "OrderTransitionTargetEnum": TRANSITION_TARGETS,
}
