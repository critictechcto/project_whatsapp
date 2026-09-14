import pytest

from apps.billing.plans import ensure_default_plans
from apps.billing.razorpay import FakeRazorpayClient, override_razorpay_client


@pytest.fixture(autouse=True)
def fake_razorpay():
    """Every billing test talks to the in-memory Razorpay; nothing reaches the network."""
    fake = FakeRazorpayClient()
    with override_razorpay_client(fake):
        yield fake


@pytest.fixture(autouse=True)
def _default_plans(request):
    """Transactional tests elsewhere flush the migration-seeded plans; restore them."""
    marker = request.node.get_closest_marker("django_db")
    if marker is None:
        return
    request.getfixturevalue("transactional_db" if marker.kwargs.get("transaction") else "db")
    ensure_default_plans()
