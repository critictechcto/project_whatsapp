from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AutomationRuleViewSet, AutomationRunViewSet, BusinessHoursViewSet

app_name = "automations"

router = SimpleRouter(use_regex_path=False)
router.register("rules", AutomationRuleViewSet, basename="rule")
router.register("runs", AutomationRunViewSet, basename="run")

urlpatterns = [
    path(
        "business-hours/",
        BusinessHoursViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="business-hours",
    ),
    *router.urls,
]
