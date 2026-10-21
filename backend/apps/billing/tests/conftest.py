import pytest
from django.core.cache import cache

from apps.billing.cashfree import FakeCashfreeClient, override_cashfree_client
from apps.billing.plans import ensure_default_plans
from apps.billing.razorpay import FakeRazorpayClient, override_razorpay_client

from .helpers import seed_razorpay_plans


@pytest.fixture(autouse=True)
def fake_razorpay():
    """Every billing test talks to the in-memory Razorpay; nothing reaches the network."""
    fake = FakeRazorpayClient()
    with override_razorpay_client(fake):
        yield fake


@pytest.fixture(autouse=True)
def fake_cashfree():
    """Every billing test talks to the in-memory Cashfree; nothing reaches the network."""
    fake = FakeCashfreeClient()
    with override_cashfree_client(fake):
        yield fake


@pytest.fixture(autouse=True)
def _default_plans(request):
    """Transactional tests elsewhere flush the migration-seeded plans; restore them. Their
    Razorpay plans are saved as already fetched; tests about fetching delete the copies."""
    marker = request.node.get_closest_marker("django_db")
    if marker is None:
        return
    request.getfixturevalue("transactional_db" if marker.kwargs.get("transaction") else "db")
    ensure_default_plans()
    seed_razorpay_plans()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Failed Razorpay plan fetches are cached; never carry them into another test."""
    cache.clear()
    yield
    cache.clear()
