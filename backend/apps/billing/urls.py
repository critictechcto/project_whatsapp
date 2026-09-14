from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    BillingProfileViewSet,
    InvoiceViewSet,
    PlanViewSet,
    SubscriptionViewSet,
    UsageViewSet,
)

app_name = "billing"

router = SimpleRouter(use_regex_path=False)
router.register("plans", PlanViewSet, basename="plan")
router.register("invoices", InvoiceViewSet, basename="invoice")

urlpatterns = [
    path("subscription/", SubscriptionViewSet.as_view({"get": "retrieve"}), name="subscription"),
    path(
        "subscription/checkout/",
        SubscriptionViewSet.as_view({"post": "checkout"}),
        name="subscription-checkout",
    ),
    path(
        "subscription/verify/",
        SubscriptionViewSet.as_view({"post": "verify"}),
        name="subscription-verify",
    ),
    path(
        "subscription/cancel/",
        SubscriptionViewSet.as_view({"post": "cancel"}),
        name="subscription-cancel",
    ),
    path(
        "billing-profile/",
        BillingProfileViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="billing-profile",
    ),
    path("usage/", UsageViewSet.as_view({"get": "retrieve"}), name="usage"),
    *router.urls,
]
