from django.urls import path

from .views import meta_callback

app_name = "webhooks"

urlpatterns = [
    path("", meta_callback, name="meta-callback"),
]
