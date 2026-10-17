from rest_framework.routers import SimpleRouter

app_name = "offers"

router = SimpleRouter(use_regex_path=False)

urlpatterns = [*router.urls]
