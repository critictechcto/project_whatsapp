from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import CounterRedeemView, OfferClaimViewSet, OfferCodeViewSet

app_name = "offers"

router = SimpleRouter(use_regex_path=False)
router.register("codes", OfferCodeViewSet, basename="code")
router.register("claims", OfferClaimViewSet, basename="claim")

urlpatterns = [
    path("redeem/", CounterRedeemView.as_view(), name="redeem"),
    *router.urls,
]
