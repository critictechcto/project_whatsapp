from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    EmbeddedSignupView,
    PhoneNumberViewSet,
    SignupConfigView,
    WhatsAppBusinessAccountViewSet,
)

app_name = "whatsapp"

router = SimpleRouter()
router.register("accounts", WhatsAppBusinessAccountViewSet, basename="account")
router.register("phone-numbers", PhoneNumberViewSet, basename="phone-number")

urlpatterns = [
    path("signup-config/", SignupConfigView.as_view(), name="signup-config"),
    path("embedded-signup/", EmbeddedSignupView.as_view(), name="embedded-signup"),
    *router.urls,
]
