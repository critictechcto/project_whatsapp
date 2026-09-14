import pytest

from apps.whatsapp.factories import WhatsAppBusinessAccountFactory


@pytest.fixture
def waba(workspace):
    return WhatsAppBusinessAccountFactory(workspace=workspace)


@pytest.fixture
def other_waba(other_workspace):
    return WhatsAppBusinessAccountFactory(workspace=other_workspace)


def flatten(detail) -> list[str]:
    """All messages in a DRF ValidationError detail as plain strings."""
    if isinstance(detail, dict):
        return [message for value in detail.values() for message in flatten(value)]
    if isinstance(detail, list):
        return [message for value in detail for message in flatten(value)]
    return [str(detail)]
