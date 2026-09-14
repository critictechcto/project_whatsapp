from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import PaymentAccountViewSet, PaymentLinkViewSet

app_name = "payments"

router = SimpleRouter(use_regex_path=False)
router.register("links", PaymentLinkViewSet, basename="link")

urlpatterns = [
    path(
        "account/",
        PaymentAccountViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="account",
    ),
    path(
        "account/verify/",
        PaymentAccountViewSet.as_view({"post": "verify"}),
        name="account-verify",
    ),
    path(
        "account/rotate-webhook/",
        PaymentAccountViewSet.as_view({"post": "rotate_webhook"}),
        name="account-rotate-webhook",
    ),
    *router.urls,
]
