"""Test helpers other apps may import.

``from apps.payments.testing import fake_payments`` in a test module (or a conftest) makes the
``fake_payments`` fixture available: every ``get_provider()`` call returns one
:class:`~apps.payments.providers.fake.FakePaymentProvider` for the test.
"""

import pytest

from .providers import override_provider
from .providers.fake import FakePaymentProvider

__all__ = ("FakePaymentProvider", "fake_payments")


@pytest.fixture
def fake_payments():
    fake = FakePaymentProvider()
    with override_provider(fake):
        yield fake
