"""Buyer return page after paying on the gateway: /pay/return/<payment_link_id>/."""

from django.urls import path

from .views import payment_return

app_name = "payments_return"

urlpatterns = [
    path("<uuid:payment_link_id>/", payment_return, name="link-return"),
]
