import inspect

import pytest

from apps.whatsapp.client import GraphClient, get_client, override_client
from apps.whatsapp.client.fake import FakeGraphClient
from apps.whatsapp.client.graph import HttpGraphClient

PROTOCOL_METHODS = sorted(
    name
    for name, member in inspect.getmembers(GraphClient, inspect.isfunction)
    if not name.startswith("_")
)


def _parameters(function):
    return [
        (param.name, param.kind, param.default)
        for param in inspect.signature(function).parameters.values()
        if param.name != "self"
    ]


@pytest.mark.parametrize("implementation", [HttpGraphClient, FakeGraphClient])
@pytest.mark.parametrize("method", PROTOCOL_METHODS)
def test_implementations_match_protocol_signatures(implementation, method):
    assert hasattr(implementation, method), f"{implementation.__name__} lacks {method}"
    assert _parameters(getattr(implementation, method)) == _parameters(getattr(GraphClient, method))


@pytest.mark.parametrize("implementation", [HttpGraphClient, FakeGraphClient])
def test_implementations_satisfy_runtime_protocol(implementation):
    assert isinstance(implementation(access_token="token"), GraphClient)


def test_get_client_uses_setting_and_override():
    client = get_client("customer-token")
    assert isinstance(client, FakeGraphClient)
    assert client.access_token == "customer-token"

    shared = FakeGraphClient()
    with override_client(shared):
        assert get_client("a") is shared
        assert shared.access_token == "a"
    assert get_client() is not shared
