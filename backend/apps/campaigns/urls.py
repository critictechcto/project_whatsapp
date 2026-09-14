from rest_framework.routers import SimpleRouter

from .views import CampaignViewSet

app_name = "campaigns"

router = SimpleRouter(use_regex_path=False)
router.register("", CampaignViewSet, basename="campaign")

urlpatterns = [*router.urls]
