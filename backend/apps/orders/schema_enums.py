"""Contract enum names for orders and the store (docs/contracts/wave-3-commerce.md and
docs/contracts/services-and-offers.md). Values only."""

SHOP_MODES = ("bot", "native_catalog")
ORDER_STATUSES = (
    "draft",
    "awaiting_confirmation",
    "awaiting_address",
    "awaiting_time",
    "awaiting_payment_method",
    "pending_payment",
    "requested",
    "confirmed",
    "packed",
    "shipped",
    "delivered",
    "completed",
    "no_show",
    "cancelled",
    "expired",
    "needs_attention",
)
ORDER_STAGES = ("checkout", "open", "closed")
PAYMENT_STATUSES = ("unpaid", "paid", "cod_pending", "cod_collected", "refunded_manual")
PAYMENT_METHODS = ("online", "cod", "pay_at_shop")
ORDER_KINDS = ("delivery", "booking")
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
    "time_requested",
    "appointment_set",
    "reminder_sent",
    "attendance_confirmed",
    "reschedule_requested",
    "offer_applied",
    "offer_removed",
)
ORDER_EVENT_ACTORS = ("buyer", "dashboard", "seller_whatsapp", "system")
# OrderTransitionRequest.to_status: the statuses a member may move an order to by hand.
# Bookings: requested (from needs_attention), confirmed (needs appointment_at), completed, no_show.
TRANSITION_TARGETS = (
    "requested",
    "confirmed",
    "packed",
    "shipped",
    "delivered",
    "completed",
    "no_show",
)

ENUM_NAME_OVERRIDES = {
    "ShopModeEnum": SHOP_MODES,
    "OrderStatusEnum": ORDER_STATUSES,
    "OrderKindEnum": ORDER_KINDS,
    "OrderStageEnum": ORDER_STAGES,
    "PaymentStatusEnum": PAYMENT_STATUSES,
    "PaymentMethodEnum": PAYMENT_METHODS,
    "OrderSourceEnum": ORDER_SOURCES,
    "OrderEventTypeEnum": ORDER_EVENT_TYPES,
    "OrderEventActorEnum": ORDER_EVENT_ACTORS,
    "OrderTransitionTargetEnum": TRANSITION_TARGETS,
}
