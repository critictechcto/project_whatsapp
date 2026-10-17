"""Code matching, collisions and discount maths."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.contacts.models import ConsentKeywords
from apps.offers import services
from apps.offers.factories import OfferCodeFactory
from apps.offers.models import OfferCode
from apps.orders.factories import StoreSettingsFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("text", ["DIWALI", "diwali", "  Diwali!  ", "diwali.", "“DIWALI”"])
def test_whole_message_matches(offer, workspace, text):
    assert services.match_code(workspace.pk, text) == offer


@pytest.mark.parametrize("text", ["diwali offer", "DIWAL", "", None, "di wali", "x" * 200])
def test_other_text_does_not_match(offer, workspace, text):
    assert services.match_code(workspace.pk, text) is None


def test_codes_with_dashes_match(workspace):
    offer = OfferCodeFactory(workspace=workspace, code="FLAT-50")
    assert services.match_code(workspace.pk, "flat-50") == offer


def test_inactive_and_out_of_date_codes_do_not_match(workspace):
    now = timezone.now()
    OfferCodeFactory(workspace=workspace, code="OFF", is_active=False)
    OfferCodeFactory(workspace=workspace, code="SOON", starts_at=now + timedelta(days=1))
    OfferCodeFactory(workspace=workspace, code="OVER", ends_at=now - timedelta(minutes=1))
    live = OfferCodeFactory(
        workspace=workspace,
        code="LIVE",
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=1),
    )

    for text in ("off", "soon", "over"):
        assert services.match_code(workspace.pk, text) is None
    assert services.match_code(workspace.pk, "live") == live


def test_codes_of_other_workspaces_do_not_match(offer, other_workspace):
    assert services.match_code(other_workspace.pk, "DIWALI") is None


def test_code_is_stored_upper_case(workspace):
    offer = OfferCodeFactory(workspace=workspace, code="holi")
    offer.refresh_from_db()
    assert offer.code == "HOLI"


# --- Collisions ---------------------------------------------------------------------------------


def test_default_menu_keywords_collide_without_store_settings(workspace):
    assert services.code_collision(workspace, "MENU")
    assert services.code_collision(workspace, "HI")


def test_custom_menu_keywords_collide(workspace):
    StoreSettingsFactory(workspace=workspace, menu_keywords=["Order Now", "mithai"])
    assert services.code_collision(workspace, "MITHAI")
    assert services.code_collision(workspace, "HI") is None


def test_consent_and_opt_out_keywords_collide(workspace):
    assert services.code_collision(workspace, "STOP")
    assert services.code_collision(workspace, "SUBSCRIBE")
    ConsentKeywords.objects.create(
        workspace=workspace, opt_in_keywords=["haan"], opt_out_keywords=["band"]
    )
    assert services.code_collision(workspace, "HAAN")
    assert services.code_collision(workspace, "BAND")
    assert services.code_collision(workspace, "STOP")
    assert services.code_collision(workspace, "DIWALI") is None


# --- Discounts ----------------------------------------------------------------------------------


def make_offer(**kwargs) -> OfferCode:
    return OfferCode(code="X", reply_text="x", **kwargs)


def test_percent_is_floored():
    offer = make_offer(discount_type="percent", discount_value=15)
    assert services.discount_for(offer, 9999) == 1499


def test_percent_is_capped():
    offer = make_offer(discount_type="percent", discount_value=50, max_discount_paise=20000)
    assert services.discount_for(offer, 100000) == 20000
    assert services.discount_for(offer, 30000) == 15000


def test_amount_leaves_at_least_one_rupee():
    offer = make_offer(discount_type="amount", discount_value=50000)
    assert services.discount_for(offer, 100000) == 50000
    assert services.discount_for(offer, 30000) == 29900
    assert services.discount_for(offer, 100) == 0
    assert services.discount_for(offer, 50) == 0


def test_no_discount_type_is_zero():
    assert services.discount_for(make_offer(discount_type="none"), 100000) == 0
