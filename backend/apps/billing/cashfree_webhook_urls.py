"""Cashfree billing webhooks, mounted at /webhooks/cashfree/billing/."""

from django.urls import path

from .views import cashfree_webhook

app_name = "billing_cashfree_webhooks"

urlpatterns = [
    path("", cashfree_webhook, name="cashfree-callback"),
]
