from django.urls import path

from .consumers import InboxConsumer

# Collected by config.routing; common.ws_auth.WS_PATH is "/ws/v1/".
websocket_urlpatterns = [
    path("ws/v1/", InboxConsumer.as_asgi()),
]
