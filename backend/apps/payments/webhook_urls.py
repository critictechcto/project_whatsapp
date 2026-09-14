"""Per-seller Razorpay webhooks: /webhooks/razorpay/merchants/<token>/."""

from django.urls import path

from .views import merchant_webhook

app_name = "payments_webhooks"

urlpatterns = [
    path("<str:token>/", merchant_webhook, name="merchant-webhook"),
]
