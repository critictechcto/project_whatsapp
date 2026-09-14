"""Native Meta catalog: available catalogs, connect/create, permissions, resync and settings."""

import pytest
from django.utils import timezone

from apps.catalog.factories import (
    MetaCatalogFactory,
    MetaCatalogPhoneSettingFactory,
    ProductFactory,
)
from apps.catalog.models import MetaCatalog, MetaCatalogPhoneSetting
from apps.whatsapp.client.errors import TransientError
from apps.whatsapp.factories import PhoneNumberFactory, WhatsAppBusinessAccountFactory
from apps.whatsapp.models import WhatsAppBusinessAccount

from .conftest import META_CATALOGS, detail

pytestmark = pytest.mark.django_db

BUSINESS_ID = "5550001"  # the fake's default owner business
CATALOG_SCOPES = {"catalog_management": [], "business_management": [BUSINESS_ID]}
AVAILABLE = f"{META_CATALOGS}available/"


@pytest.fixture
def waba(workspace, fake_graph):
    waba = WhatsAppBusinessAccountFactory(workspace=workspace, business_id="")
    fake_graph.add_waba(waba.waba_id)
    return waba


@pytest.fixture
def number(waba):
    return PhoneNumberFactory(waba=waba, phone_e164="+919812345678", is_default=True)


def grant(fake_graph, waba, scopes=CATALOG_SCOPES) -> None:
    fake_graph.add_signup(
        f"code-{waba.pk}", waba_id=waba.waba_id, token=waba.access_token, extra_scopes=scopes
    )


def assert_conflict(response, code: str) -> dict:
    assert response.status_code == 409, response.content
    error = response.json()["error"]
    assert error["code"] == code
    return error


# --- Available catalogs -------------------------------------------------------------------------


def test_available_lists_catalogs_owned_by_the_business(admin, waba, fake_graph):
    grant(fake_graph, waba)
    fake_graph.add_catalog("111", name="Sharma Sweets")
    fake_graph.add_catalog("222", business_id="999", name="Someone else")

    response = admin.get(AVAILABLE, {"waba_id": str(waba.pk)})

    assert response.status_code == 200, response.content
    assert response.json() == [{"id": "111", "name": "Sharma Sweets"}]


def test_available_needs_catalog_permissions(admin, waba, fake_graph):
    grant(fake_graph, waba, scopes={"business_management": [BUSINESS_ID]})

    error = assert_conflict(
        admin.get(AVAILABLE, {"waba_id": str(waba.pk)}), "catalog_permissions_missing"
    )

    assert error["details"] == {"reconnect_url": None}
    assert fake_graph.calls_to("list_business_catalogs") == []


def test_available_validates_the_account(admin, other_workspace, fake_graph):
    foreign = WhatsAppBusinessAccountFactory(workspace=other_workspace)

    assert admin.get(AVAILABLE).status_code == 400
    assert admin.get(AVAILABLE, {"waba_id": str(foreign.pk)}).status_code == 400


# --- Connect ----------------------------------------------------------------------------------


def test_connect_an_existing_catalog(
    admin, workspace, waba, number, fake_graph, django_capture_on_commit_callbacks
):
    grant(fake_graph, waba)
    fake_graph.add_catalog("111", name="Sharma Sweets")
    ProductFactory(workspace=workspace, sku="KAJU-1", image="catalog/kaju.jpg")

    with django_capture_on_commit_callbacks(execute=True):
        response = admin.post(
            META_CATALOGS, {"waba_id": str(waba.pk), "catalog_id": "111"}, format="json"
        )

    assert response.status_code == 201, response.content
    data = response.json()
    assert (data["catalog_id"], data["catalog_name"], data["status"]) == (
        "111",
        "Sharma Sweets",
        "connected",
    )
    assert data["waba"]["id"] == str(waba.pk)
    assert data["phone_numbers"] == [
        {
            "phone_number_id": str(number.pk),
            "display_phone_number": number.display_phone_number,
            "is_cart_enabled": True,
            "is_catalog_visible": False,
        }
    ]
    [connect] = fake_graph.calls_to("connect_catalog")
    assert connect.kwargs == {"waba_id": waba.waba_id, "catalog_id": "111"}
    assert connect.access_token == waba.access_token
    meta_catalog = MetaCatalog.objects.get(pk=data["id"])
    assert meta_catalog.business_id == BUSINESS_ID
    assert meta_catalog.last_synced_at is not None
    # The full sync ran on commit.
    [batch] = fake_graph.calls_to("batch_catalog_items")
    assert [request["data"]["id"] for request in batch.kwargs["requests"]] == ["KAJU-1"]


def test_connect_create_a_catalog(admin, waba, number, fake_graph):
    grant(fake_graph, waba)

    response = admin.post(
        META_CATALOGS, {"waba_id": str(waba.pk), "create_name": "Sharma Sweets"}, format="json"
    )

    assert response.status_code == 201, response.content
    [create] = fake_graph.calls_to("create_catalog")
    assert create.kwargs == {"business_id": BUSINESS_ID, "name": "Sharma Sweets"}
    catalog_id = response.json()["catalog_id"]
    assert fake_graph.calls_to("connect_catalog")[0].kwargs["catalog_id"] == catalog_id
    assert fake_graph.list_waba_catalogs(waba.waba_id)[0]["id"] == catalog_id


def test_connect_rejects_catalogs_the_business_does_not_own(admin, waba, fake_graph):
    grant(fake_graph, waba)
    fake_graph.add_catalog("222", business_id="999")

    response = admin.post(
        META_CATALOGS, {"waba_id": str(waba.pk), "catalog_id": "222"}, format="json"
    )

    assert response.status_code == 400, response.content
    assert "catalog_id" in response.json()["error"]["details"]
    assert not MetaCatalog.objects.exists()


@pytest.mark.parametrize(
    "extra", [{}, {"catalog_id": "111", "create_name": "Shop"}], ids=["neither", "both"]
)
def test_connect_needs_exactly_one_target(admin, waba, fake_graph, extra):
    response = admin.post(META_CATALOGS, {"waba_id": str(waba.pk), **extra}, format="json")

    assert response.status_code == 400, response.content
    assert fake_graph.calls == []


def test_connect_without_catalog_permissions(admin, waba, fake_graph):
    grant(fake_graph, waba, scopes=None)

    response = admin.post(
        META_CATALOGS, {"waba_id": str(waba.pk), "create_name": "Shop"}, format="json"
    )

    assert_conflict(response, "catalog_permissions_missing")
    assert fake_graph.calls_to("create_catalog") == []
    assert not MetaCatalog.objects.exists()


def test_connect_needs_a_connected_account(admin, waba, fake_graph):
    waba.status = WhatsAppBusinessAccount.Status.DISCONNECTED
    waba.save()

    response = admin.post(
        META_CATALOGS, {"waba_id": str(waba.pk), "create_name": "Shop"}, format="json"
    )

    assert_conflict(response, "whatsapp_not_connected")
    assert fake_graph.calls == []


def test_connect_maps_meta_outages(admin, waba, fake_graph):
    grant(fake_graph, waba)
    fake_graph.add_catalog("111")
    fake_graph.fail("connect_catalog", TransientError("Service unavailable", code=2))

    response = admin.post(
        META_CATALOGS, {"waba_id": str(waba.pk), "catalog_id": "111"}, format="json"
    )

    assert response.status_code == 503, response.content
    assert not MetaCatalog.objects.exists()


def test_connecting_another_catalog_resets_product_sync(admin, workspace, waba, number, fake_graph):
    grant(fake_graph, waba)
    fake_graph.add_catalog("111")
    fake_graph.add_catalog("333", waba_id=waba.waba_id)
    MetaCatalogFactory(waba=waba, catalog_id="333", last_synced_at=timezone.now())
    product = ProductFactory(
        workspace=workspace, meta_sync_status="synced", meta_review_status="approved"
    )

    response = admin.post(
        META_CATALOGS, {"waba_id": str(waba.pk), "catalog_id": "111"}, format="json"
    )

    assert response.status_code == 200, response.content
    assert MetaCatalog.objects.get().catalog_id == "111"
    product.refresh_from_db()
    assert (product.meta_sync_status, product.meta_review_status) == ("not_synced", "none")


# --- Disconnect, resync, commerce settings ----------------------------------------------------


def test_disconnect_is_local_and_resets_products(admin, workspace, fake_graph):
    meta_catalog = MetaCatalogFactory(waba__workspace=workspace)
    product = ProductFactory(
        workspace=workspace,
        meta_sync_status="synced",
        meta_review_status="rejected",
        meta_rejection_reasons=["POLICY"],
        meta_product_id="600001",
    )

    assert admin.delete(detail(META_CATALOGS, meta_catalog)).status_code == 204

    assert not MetaCatalog.objects.exists()
    product.refresh_from_db()
    assert (product.meta_sync_status, product.meta_review_status) == ("not_synced", "none")
    assert (product.meta_rejection_reasons, product.meta_product_id) == ([], "")
    assert fake_graph.calls == []


def test_sync_queues_a_full_resync(
    admin, workspace, connected, fake_graph, django_capture_on_commit_callbacks
):
    ProductFactory(workspace=workspace, sku="OLD-1", image="catalog/old.jpg")
    connected.last_synced_at = timezone.now()
    connected.save()

    with django_capture_on_commit_callbacks(execute=True):
        response = admin.post(detail(META_CATALOGS, connected, "sync/"))

    assert response.status_code == 202, response.content
    [batch] = fake_graph.calls_to("batch_catalog_items")
    assert [request["data"]["id"] for request in batch.kwargs["requests"]] == ["OLD-1"]


def test_sync_rechecks_lost_permissions(admin, connected, fake_graph):
    connected.status = MetaCatalog.Status.PERMISSIONS_MISSING
    connected.save()

    assert_conflict(
        admin.post(detail(META_CATALOGS, connected, "sync/")), "catalog_permissions_missing"
    )

    grant(fake_graph, connected.waba)
    response = admin.post(detail(META_CATALOGS, connected, "sync/"))
    assert response.status_code == 202, response.content
    assert response.json()["status"] == "connected"


def test_update_commerce_settings(admin, connected, fake_graph):
    number = connected.waba.phone_numbers.get()

    response = admin.patch(
        detail(META_CATALOGS, connected, "commerce-settings/"),
        {"phone_number_id": str(number.pk), "is_catalog_visible": True},
        format="json",
    )

    assert response.status_code == 200, response.content
    [update] = fake_graph.calls_to("update_commerce_settings")
    assert update.kwargs == {
        "phone_number_id": number.phone_number_id,
        "is_cart_enabled": None,
        "is_catalog_visible": True,
    }
    setting = MetaCatalogPhoneSetting.objects.get(phone_number=number)
    assert (setting.is_cart_enabled, setting.is_catalog_visible) == (True, True)
    [row] = response.json()["phone_numbers"]
    assert (row["is_cart_enabled"], row["is_catalog_visible"]) == (True, True)


def test_update_commerce_settings_keeps_stored_flags(admin, connected, fake_graph):
    number = connected.waba.phone_numbers.get()
    MetaCatalogPhoneSettingFactory(
        meta_catalog=connected, phone_number=number, is_cart_enabled=False, is_catalog_visible=True
    )

    response = admin.patch(
        detail(META_CATALOGS, connected, "commerce-settings/"),
        {"phone_number_id": str(number.pk), "is_cart_enabled": True},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert fake_graph.calls_to("get_commerce_settings") == []
    setting = MetaCatalogPhoneSetting.objects.get(phone_number=number)
    assert (setting.is_cart_enabled, setting.is_catalog_visible) == (True, True)


def test_commerce_settings_need_a_number_on_the_catalog_account(admin, workspace, connected):
    elsewhere = PhoneNumberFactory(waba=WhatsAppBusinessAccountFactory(workspace=workspace))

    response = admin.patch(
        detail(META_CATALOGS, connected, "commerce-settings/"),
        {"phone_number_id": str(elsewhere.pk), "is_cart_enabled": True},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "phone_number_id" in response.json()["error"]["details"]
