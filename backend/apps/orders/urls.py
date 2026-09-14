from rest_framework.routers import SimpleRouter

from .views import OrderViewSet

app_name = "orders"

router = SimpleRouter(use_regex_path=False)
router.register("", OrderViewSet, basename="order")

urlpatterns = [*router.urls]
