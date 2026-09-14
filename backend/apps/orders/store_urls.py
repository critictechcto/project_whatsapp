from django.urls import path

from .views import StoreViewSet

app_name = "store"

urlpatterns = [
    path(
        "settings/",
        StoreViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="settings",
    ),
    path("checklist/", StoreViewSet.as_view({"get": "checklist"}), name="checklist"),
    path(
        "starter-templates/",
        StoreViewSet.as_view({"post": "starter_templates"}),
        name="starter-templates",
    ),
]
