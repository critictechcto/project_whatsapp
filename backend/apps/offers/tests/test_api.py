"""Offers API: codes CRUD, stats, claims, redemption, roles, isolation and plan gating."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.factories import ProductFactory
from apps.contacts.models import Contact
from apps.offers.factories import OfferClaimFactory, OfferCodeFactory
from apps.offers.models import OfferClaim, OfferCode
from common.roles import Role
from common.testing import assert_tenant_isolated

pytestmark = pytest.mark.django_db

CODES = "/api/v1/offers/codes/"
CLAIMS = "/api/v1/offers/claims/"
REDEEM = "/api/v1/offers/redeem/"

NEW_CODE = {
    "code": "holi25",
    "title": "Holi offer",
    "reply_text": "Happy Holi! 25% off up to ₹300.",
    "discount_type": "percent",
    "discount_value": 25,
    "max_discount_paise": 30000,
    "applies_to": "all",
}


def error_code(response) -> str:
    return response.json()["error"]["code"]


# --- Codes --------------------------------------------------------------------------------------


def test_create_list_update_and_delete(auth_client):
    client = auth_client(Role.ADMIN)

    created = client.post(CODES, NEW_CODE, format="json")
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["code"] == "HOLI25"
    assert body["claims_count"] == 0 and body["redeemed_count"] == 0
    assert body["max_uses_per_contact"] == 1 and body["is_active"] is True

    listed = client.get(CODES)
    assert listed.status_code == 200
    assert [row["code"] for row in listed.json()["results"]] == ["HOLI25"]

    url = f"{CODES}{body['id']}/"
    patched = client.patch(url, {"is_active": False, "title": "Holi"}, format="json")
    assert patched.status_code == 200, patched.content
    assert patched.json()["is_active"] is False

    assert client.delete(url).status_code == 204
    assert not OfferCode.objects.exists()


def test_counters(auth_client, offer):
    OfferClaimFactory(offer=offer)
    OfferClaimFactory(offer=offer, status="redeemed")

    row = auth_client(Role.VIEWER).get(CODES).json()["results"][0]
    assert (row["claims_count"], row["redeemed_count"]) == (2, 1)
    detail = auth_client(Role.VIEWER).get(f"{CODES}{offer.pk}/").json()
    assert (detail["claims_count"], detail["redeemed_count"]) == (2, 1)


def test_delete_with_claims_is_offer_in_use(auth_client, offer):
    OfferClaimFactory(offer=offer)
    response = auth_client(Role.ADMIN).delete(f"{CODES}{offer.pk}/")
    assert response.status_code == 409
    assert error_code(response) == "offer_in_use"


@pytest.mark.parametrize("code", ["menu", "HI", "Stop", "subscribe", "a", "has space", "x" * 21])
def test_invalid_or_colliding_codes(auth_client, code):
    response = auth_client(Role.ADMIN).post(CODES, {**NEW_CODE, "code": code}, format="json")
    assert response.status_code == 400
    assert "code" in response.json()["error"]["details"]


def test_duplicate_code(auth_client, offer):
    response = auth_client(Role.ADMIN).post(CODES, {**NEW_CODE, "code": "diwali"}, format="json")
    assert response.status_code == 400
    assert "code" in response.json()["error"]["details"]


def test_renaming_keeps_own_code(auth_client, offer):
    response = auth_client(Role.ADMIN).patch(
        f"{CODES}{offer.pk}/", {"code": "Diwali"}, format="json"
    )
    assert response.status_code == 200, response.content


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"discount_type": "percent", "discount_value": 91}, "discount_value"),
        ({"discount_type": "percent", "discount_value": 0}, "discount_value"),
        (
            {"discount_type": "amount", "discount_value": 99, "max_discount_paise": None},
            "discount_value",
        ),
        ({"discount_type": "amount", "discount_value": 5000}, "max_discount_paise"),
        ({"max_uses_per_contact": 0}, "max_uses_per_contact"),
        ({"reply_text": ""}, "reply_text"),
        ({"reply_text": "x" * 901}, "reply_text"),
        ({"title": "x" * 61}, "title"),
    ],
)
def test_validation(auth_client, changes, field):
    response = auth_client(Role.ADMIN).post(CODES, {**NEW_CODE, **changes}, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


def test_dates_must_be_ordered(auth_client):
    now = timezone.now()
    payload = {
        **NEW_CODE,
        "starts_at": now.isoformat(),
        "ends_at": (now - timedelta(1)).isoformat(),
    }
    response = auth_client(Role.ADMIN).post(CODES, payload, format="json")
    assert response.status_code == 400
    assert "ends_at" in response.json()["error"]["details"]


def test_no_discount_zeroes_the_value(auth_client):
    payload = {**NEW_CODE, "discount_type": "none"}
    response = auth_client(Role.ADMIN).post(CODES, payload, format="json")
    assert response.status_code == 201, response.content
    assert response.json()["discount_value"] == 0
    assert response.json()["max_discount_paise"] is None


@pytest.mark.parametrize("role", [Role.VIEWER, Role.AGENT])
def test_only_admins_write_codes(auth_client, offer, role):
    client = auth_client(role)
    assert client.get(CODES).status_code == 200
    assert client.post(CODES, NEW_CODE, format="json").status_code == 403
    assert client.patch(f"{CODES}{offer.pk}/", {"title": "x"}, format="json").status_code == 403
    assert client.delete(f"{CODES}{offer.pk}/").status_code == 403


def test_codes_are_tenant_isolated(auth_client, offer, other_workspace):
    assert_tenant_isolated(
        auth_client(workspace=other_workspace),
        object_id=offer.pk,
        list_url=CODES,
        detail_url=f"{CODES}{offer.pk}/",
    )


def test_writes_need_commerce(auth_client, offer, no_commerce):
    client = auth_client(Role.ADMIN)
    assert client.get(CODES).status_code == 200
    response = client.post(CODES, NEW_CODE, format="json")
    assert response.status_code == 409
    assert error_code(response) == "feature_not_available"
    claim = OfferClaimFactory(offer=offer)
    response = client.post(f"{CLAIMS}{claim.pk}/redeem/", {}, format="json")
    assert error_code(response) == "feature_not_available"
    response = client.post(REDEEM, {"code": "DIWALI", "phone": "9876543210"}, format="json")
    assert error_code(response) == "feature_not_available"


# --- Stats --------------------------------------------------------------------------------------


def test_stats(auth_client, offer):
    OfferClaimFactory(offer=offer, ad_source_id="ad-1")
    OfferClaimFactory(offer=offer, ctwa_clid="clid", status="applied", discount_paise=5000)
    OfferClaimFactory(
        offer=offer,
        status="redeemed",
        discount_paise=3000,
        bill_paise=30000,
        redeemed_at=timezone.now(),
    )
    OfferClaimFactory(
        offer=offer,
        status="redeemed",
        discount_paise=2000,
        bill_paise=20000,
        redeemed_at=timezone.now(),
    )
    OfferClaimFactory(offer=OfferCodeFactory(workspace=offer.workspace), status="redeemed")

    response = auth_client(Role.VIEWER).get(f"{CODES}{offer.pk}/stats/")

    assert response.status_code == 200, response.content
    body = response.json()
    assert {k: v for k, v in body.items() if k != "daily"} == {
        "claims": 4,
        "from_ads": 2,
        "applied": 1,
        "redeemed": 2,
        "discount_paise": 5000,
        "revenue_paise": 50000,
    }
    assert len(body["daily"]) == 30
    assert body["daily"][-1]["claims"] == 4
    assert body["daily"][-1]["redeemed"] == 2
    assert sum(day["claims"] for day in body["daily"]) == 4


# --- Claims -------------------------------------------------------------------------------------


def test_claims_list_and_filters(auth_client, offer, workspace):
    other_offer = OfferCodeFactory(workspace=workspace, code="HOLI")
    first = OfferClaimFactory(offer=offer, contact__phone_e164="+919800000001")
    OfferClaimFactory(offer=offer, status="redeemed", contact__phone_e164="+919800000002")
    OfferClaimFactory(offer=other_offer, contact__phone_e164="+919800000003")
    client = auth_client(Role.VIEWER)

    rows = client.get(CLAIMS).json()["results"]
    assert len(rows) == 3
    row = next(r for r in rows if r["id"] == str(first.pk))
    assert row["offer"] == str(offer.pk)
    assert row["offer_code"] == "DIWALI"
    assert row["contact"]["phone_e164"] == "+919800000001"
    assert row["order_id"] is None and row["order_number"] is None

    assert len(client.get(CLAIMS, {"offer": str(offer.pk)}).json()["results"]) == 2
    assert len(client.get(CLAIMS, {"status": "redeemed"}).json()["results"]) == 1
    assert [r["id"] for r in client.get(CLAIMS, {"phone": "0000001"}).json()["results"]] == [
        str(first.pk)
    ]
    assert client.get(CLAIMS, {"status": "nope"}).status_code == 400
    assert client.get(CLAIMS, {"offer": "nope"}).status_code == 400


def test_claims_are_tenant_isolated(auth_client, offer, other_workspace):
    claim = OfferClaimFactory(offer=offer)
    client = auth_client(workspace=other_workspace)
    assert_tenant_isolated(client, object_id=claim.pk, list_url=CLAIMS)
    response = client.post(f"{CLAIMS}{claim.pk}/redeem/", {}, format="json")
    assert response.status_code == 404


def test_agent_redeems_a_claim(auth_client, offer):
    claim = OfferClaimFactory(offer=offer)
    client = auth_client(Role.AGENT)

    response = client.post(f"{CLAIMS}{claim.pk}/redeem/", {"bill_paise": 45000}, format="json")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "redeemed"
    assert body["bill_paise"] == 45000
    assert body["redeemed_by"] is not None
    assert body["redeemed_at"] is not None

    again = client.post(f"{CLAIMS}{claim.pk}/redeem/", {}, format="json")
    assert again.status_code == 409
    assert error_code(again) == "invalid_transition"


def test_viewer_cannot_redeem(auth_client, offer):
    claim = OfferClaimFactory(offer=offer)
    client = auth_client(Role.VIEWER)
    assert client.post(f"{CLAIMS}{claim.pk}/redeem/", {}, format="json").status_code == 403
    assert client.post(REDEEM, {"code": "DIWALI", "phone": "9876543210"}).status_code == 403


# --- Counter redemption -------------------------------------------------------------------------


def test_counter_redeem_creates_the_contact_and_claim(auth_client, offer, workspace):
    response = auth_client(Role.AGENT).post(
        REDEEM, {"code": " diwali ", "phone": "98765 43210", "bill_paise": 120000}, format="json"
    )

    assert response.status_code == 201, response.content
    contact = Contact.objects.get(workspace=workspace, phone_e164="+919876543210")
    claim = OfferClaim.objects.get()
    assert claim.contact == contact
    assert claim.status == "redeemed"
    assert claim.bill_paise == 120000
    assert claim.conversation is None and claim.message is None
    assert response.json()["id"] == str(claim.pk)


def test_counter_redeem_uses_the_open_claim(auth_client, offer, contact):
    claim = OfferClaimFactory(offer=offer, contact=contact)

    response = auth_client(Role.AGENT).post(
        REDEEM, {"code": "DIWALI", "phone": contact.phone_e164}, format="json"
    )

    assert response.status_code == 201, response.content
    assert response.json()["id"] == str(claim.pk)
    assert OfferClaim.objects.count() == 1
    claim.refresh_from_db()
    assert claim.status == "redeemed"


def test_counter_redeem_respects_the_per_contact_limit(auth_client, offer, contact):
    OfferClaimFactory(offer=offer, contact=contact, status="redeemed")
    response = auth_client(Role.AGENT).post(
        REDEEM, {"code": "DIWALI", "phone": contact.phone_e164}, format="json"
    )
    assert response.status_code == 409
    assert error_code(response) == "offer_unavailable"


def test_counter_redeem_rejects_inactive_offers(auth_client, offer):
    offer.is_active = False
    offer.save()
    response = auth_client(Role.AGENT).post(
        REDEEM, {"code": "DIWALI", "phone": "9876543210"}, format="json"
    )
    assert response.status_code == 409
    assert error_code(response) == "offer_unavailable"


def test_counter_redeem_rejects_used_up_offers(auth_client, offer):
    offer.max_uses = 1
    offer.save()
    OfferClaimFactory(offer=offer, status="redeemed")
    response = auth_client(Role.AGENT).post(
        REDEEM, {"code": "DIWALI", "phone": "9876543210"}, format="json"
    )
    assert response.status_code == 409
    assert error_code(response) == "offer_unavailable"


def test_counter_redeem_validates_code_and_phone(auth_client, offer):
    client = auth_client(Role.AGENT)
    response = client.post(REDEEM, {"code": "NOPE", "phone": "9876543210"}, format="json")
    assert response.status_code == 400
    assert "code" in response.json()["error"]["details"]
    response = client.post(REDEEM, {"code": "DIWALI", "phone": "12"}, format="json")
    assert response.status_code == 400
    assert "phone" in response.json()["error"]["details"]


# --- Chosen items -------------------------------------------------------------------------------


def test_items_offer_keeps_its_chosen_items(auth_client, workspace):
    client = auth_client(Role.ADMIN)
    facial = ProductFactory(workspace=workspace, name="Diwali Glow facial", kind="service")

    created = client.post(
        CODES, {**NEW_CODE, "applies_to": "items", "product_ids": [str(facial.pk)]}, format="json"
    )

    assert created.status_code == 201, created.content
    assert [item["name"] for item in created.json()["products"]] == ["Diwali Glow facial"]
    assert created.json()["products"][0]["kind"] == "service"
    url = f"{CODES}{created.json()['id']}/"
    patched = client.patch(url, {"title": "Glow"}, format="json")
    assert patched.status_code == 200, patched.content
    assert len(patched.json()["products"]) == 1

    switched = client.patch(url, {"applies_to": "all"}, format="json")
    assert switched.json()["products"] == []


def test_items_offer_needs_items_of_this_workspace(auth_client, other_workspace):
    client = auth_client(Role.ADMIN)

    empty = client.post(CODES, {**NEW_CODE, "applies_to": "items"}, format="json")
    assert empty.status_code == 400
    assert "product_ids" in empty.json()["error"]["details"]

    foreign = ProductFactory(workspace=other_workspace)
    stolen = client.post(
        CODES, {**NEW_CODE, "applies_to": "items", "product_ids": [str(foreign.pk)]}, format="json"
    )
    assert stolen.status_code == 400
    assert "product_ids" in stolen.json()["error"]["details"]
