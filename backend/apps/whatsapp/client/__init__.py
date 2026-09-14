"""Meta Graph API access. Always go through :func:`get_client`; never call httpx directly.

``settings.WHATSAPP_GRAPH_CLIENT`` picks the implementation (HttpGraphClient in dev/prod,
FakeGraphClient in tests). Tests use the ``fake_graph`` fixture, which installs one shared fake
via :func:`override_client`.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from django.conf import settings
from django.utils.module_loading import import_string

from .base import JSON, GraphClient
from .errors import GraphAPIError

__all__ = ("JSON", "GraphAPIError", "GraphClient", "get_client", "override_client")

_override: GraphClient | None = None


def get_client(access_token: str | None = None) -> GraphClient:
    """Client bound to a customer's token, or app-level (``None``) for code exchange/debug."""
    if _override is not None:
        _override.access_token = access_token
        return _override
    client_class = import_string(settings.WHATSAPP_GRAPH_CLIENT)
    return client_class(access_token=access_token)


@contextmanager
def override_client(client: GraphClient) -> Iterator[GraphClient]:
    global _override
    previous = _override
    _override = client
    try:
        yield client
    finally:
        _override = previous
