import pytest

from apps.offers import demo
from apps.offers.models import OfferClaim, OfferCode

pytestmark = pytest.mark.django_db


def test_seed_is_idempotent(workspace):
    demo.seed(workspace)
    demo.seed(workspace)

    offer = OfferCode.objects.get(workspace=workspace)
    assert offer.code == "DIWALI"
    assert OfferClaim.objects.filter(offer=offer).count() == len(demo.CLAIMS)
    assert OfferClaim.objects.filter(offer=offer, status="redeemed").count() == 2
