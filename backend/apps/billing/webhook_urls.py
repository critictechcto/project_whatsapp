"""Razorpay webhooks, mounted at /webhooks/razorpay/."""

from django.urls import path

from .views import razorpay_webhook

app_name = "billing_webhooks"

urlpatterns = [
    path("", razorpay_webhook, name="razorpay-callback"),
]
