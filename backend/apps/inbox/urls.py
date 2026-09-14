from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ConversationViewSet, MediaAssetViewSet, MessageViewSet, WsTicketView

app_name = "inbox"

router = SimpleRouter(use_regex_path=False)
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("messages", MessageViewSet, basename="message")
router.register("media", MediaAssetViewSet, basename="media")

urlpatterns = [
    path("ws-ticket/", WsTicketView.as_view(), name="ws-ticket"),
    *router.urls,
]
