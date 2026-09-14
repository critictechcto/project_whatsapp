"""The ASGI/WSGI modules must import cleanly: servers load them before anything else."""

from django.core.handlers.wsgi import WSGIHandler


def test_asgi_exposes_protocol_router():
    from channels.routing import ProtocolTypeRouter

    from config import asgi

    assert isinstance(asgi.application, ProtocolTypeRouter)
    assert set(asgi.application.application_mapping) == {"http", "websocket"}


def test_wsgi_exposes_application():
    from config import wsgi

    assert isinstance(wsgi.application, WSGIHandler)
