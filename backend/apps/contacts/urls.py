from rest_framework.routers import SimpleRouter

from .views import ContactImportViewSet, ContactViewSet, TagViewSet

app_name = "contacts"

router = SimpleRouter()
router.register("tags", TagViewSet, basename="tag")
router.register("imports", ContactImportViewSet, basename="import")
router.register("", ContactViewSet, basename="contact")

urlpatterns = [*router.urls]
