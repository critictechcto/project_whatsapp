import pytest
from django.core.cache import cache

from apps.inbox.factories import ConversationFactory

from .helpers import NOW


@pytest.fixture(autouse=True)
def _clear_report_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def frozen(time_machine):
    time_machine.move_to(NOW, tick=False)
    return NOW


@pytest.fixture
def client(frozen, auth_client):
    """The workspace owner, with the clock frozen on 2026-03-15 IST."""
    return auth_client()


@pytest.fixture
def conversation(workspace):
    return ConversationFactory(workspace=workspace)
