from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ConsentKeywordsViewSet, ContactImportViewSet, ContactViewSet, TagViewSet

app_name = "contacts"

router = SimpleRouter()
router.register("tags", TagViewSet, basename="tag")
router.register("imports", ContactImportViewSet, basename="import")
router.register("", ContactViewSet, basename="contact")

urlpatterns = [
    path(
        "consent-keywords/",
        ConsentKeywordsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="consent-keywords",
    ),
    *router.urls,
]
