from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AlertRecipientViewSet, PlatformAlertsViewSet

app_name = "seller_alerts"

router = SimpleRouter(use_regex_path=False)
router.register("recipients", AlertRecipientViewSet, basename="recipient")

urlpatterns = [
    path("platform/", PlatformAlertsViewSet.as_view({"get": "retrieve"}), name="platform"),
    *router.urls,
]
