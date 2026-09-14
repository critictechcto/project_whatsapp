"""Catalog API: the implemented reads, role gates, stubs and tenant isolation."""

import pytest

from apps.catalog.factories import (
    CollectionFactory,
    MetaCatalogFactory,
    MetaCatalogPhoneSettingFactory,
    ProductFactory,
)
from apps.whatsapp.factories import PhoneNumberFactory
from common.roles import Role
from common.testing import assert_tenant_isolated, result_ids

pytestmark = pytest.mark.django_db

BASE = "/api/v1/catalog"
PRODUCTS = f"{BASE}/products/"
COLLECTIONS = f"{BASE}/collections/"
META_CATALOGS = f"{BASE}/meta-catalogs/"


def detail(base: str, obj, suffix: str = "") -> str:
    return f"{base}{obj.pk}/{suffix}"


def test_products_are_ordered_by_position_then_name(auth_client, workspace):
    second = ProductFactory(workspace=workspace, position=1, name="Barfi")
    third = ProductFactory(workspace=workspace, position=1, name="Chikki")
    first = ProductFactory(workspace=workspace, position=0, name="Zarda")

    response = auth_client(Role.VIEWER).get(PRODUCTS)

    assert response.status_code == 200, response.content
    assert [item["id"] for item in response.json()["results"]] == [
        str(first.pk),
        str(second.pk),
        str(third.pk),
    ]


def test_product_shape(auth_client, workspace):
    collection = CollectionFactory(workspace=workspace, name="Sweets")
    product = ProductFactory(
        workspace=workspace,
        collection=collection,
        price_paise=50000,
        sale_price_paise=45000,
        stock_qty=4,
        meta_rejection_reasons=["IMAGE_TOO_SMALL"],
    )

    response = auth_client(Role.VIEWER).get(detail(PRODUCTS, product))

    assert response.status_code == 200, response.content
    data = response.json()
    assert data["collection"] == {"id": str(collection.pk), "name": "Sweets"}
    assert data["effective_price_paise"] == 45000
    assert data["currency"] == "INR"
    assert data["image_url"] is None
    assert data["stock_qty"] == 4
    assert data["meta_sync_status"] == "not_synced"
    assert data["meta_review_status"] == "none"
    assert data["meta_rejection_reasons"] == ["IMAGE_TOO_SMALL"]


def test_product_image_url_is_absolute(auth_client, workspace):
    product = ProductFactory(workspace=workspace)
    product.image.name = f"catalog/products/{workspace.pk}/ab/abcdef.jpg"
    product.save(update_fields=["image"])

    data = auth_client(Role.VIEWER).get(detail(PRODUCTS, product)).json()

    assert data["image_url"] == (
        f"https://media.testserver/catalog/products/{workspace.pk}/ab/abcdef.jpg"
    )


def test_product_filters(auth_client, workspace):
    sweets = CollectionFactory(workspace=workspace)
    in_collection = ProductFactory(workspace=workspace, collection=sweets, sku="LADDU-1")
    loose = ProductFactory(workspace=workspace, name="Masala chai")
    hidden = ProductFactory(workspace=workspace, is_active=False)
    sold_out = ProductFactory(
        workspace=workspace, availability="out_of_stock", meta_review_status="rejected"
    )
    client = auth_client(Role.VIEWER)

    assert result_ids(client.get(PRODUCTS, {"collection": str(sweets.pk)})) == {
        str(in_collection.pk)
    }
    assert str(in_collection.pk) not in result_ids(client.get(PRODUCTS, {"collection": "none"}))
    assert result_ids(client.get(PRODUCTS, {"is_active": "false"})) == {str(hidden.pk)}
    assert result_ids(client.get(PRODUCTS, {"availability": "out_of_stock"})) == {str(sold_out.pk)}
    assert result_ids(client.get(PRODUCTS, {"meta_review_status": "rejected"})) == {
        str(sold_out.pk)
    }
    assert result_ids(client.get(PRODUCTS, {"search": "laddu"})) == {str(in_collection.pk)}
    assert result_ids(client.get(PRODUCTS, {"search": "CHAI"})) == {str(loose.pk)}


@pytest.mark.parametrize(
    "params",
    [{"availability": "maybe"}, {"is_active": "perhaps"}, {"collection": "abc"}],
)
def test_product_filters_are_validated(auth_client, workspace, params):
    assert auth_client(Role.VIEWER).get(PRODUCTS, params).status_code == 400


def test_collections_list_counts_products(auth_client, workspace):
    sweets = CollectionFactory(workspace=workspace, position=0)
    empty = CollectionFactory(workspace=workspace, position=1)
    ProductFactory.create_batch(2, workspace=workspace, collection=sweets)

    response = auth_client(Role.VIEWER).get(COLLECTIONS)

    assert response.status_code == 200, response.content
    counts = {item["id"]: item["product_count"] for item in response.json()["results"]}
    assert counts == {str(sweets.pk): 2, str(empty.pk): 0}
    assert auth_client(Role.VIEWER).get(detail(COLLECTIONS, sweets)).json()["product_count"] == 2


def test_meta_catalog_shape(auth_client, workspace):
    meta_catalog = MetaCatalogFactory(waba__workspace=workspace)
    number = PhoneNumberFactory(workspace=workspace, waba=meta_catalog.waba)
    other_number = PhoneNumberFactory(workspace=workspace, waba=meta_catalog.waba)
    MetaCatalogPhoneSettingFactory(
        meta_catalog=meta_catalog, phone_number=number, is_cart_enabled=True
    )
    ProductFactory(workspace=workspace, meta_sync_status="synced", meta_review_status="approved")
    ProductFactory(workspace=workspace, meta_sync_status="failed")

    response = auth_client(Role.VIEWER).get(META_CATALOGS)

    assert response.status_code == 200, response.content
    [data] = response.json()["results"]
    assert data["id"] == str(meta_catalog.pk)
    assert data["waba"]["id"] == str(meta_catalog.waba_id)
    assert data["status"] == "connected"
    assert data["product_counts"] == {
        "synced": 1,
        "pending": 0,
        "failed": 1,
        "approved": 1,
        "rejected": 0,
    }
    settings_by_number = {row["phone_number_id"]: row for row in data["phone_numbers"]}
    assert settings_by_number[str(number.pk)]["is_cart_enabled"] is True
    assert settings_by_number[str(other_number.pk)] == {
        "phone_number_id": str(other_number.pk),
        "display_phone_number": other_number.display_phone_number,
        "is_cart_enabled": False,
        "is_catalog_visible": False,
    }
    assert auth_client(Role.VIEWER).get(detail(META_CATALOGS, meta_catalog)).status_code == 200


def test_catalog_is_tenant_isolated(auth_client, workspace, other_workspace):
    product = ProductFactory(workspace=workspace)
    collection = CollectionFactory(workspace=workspace)
    meta_catalog = MetaCatalogFactory(waba__workspace=workspace)
    client = auth_client(workspace=other_workspace)

    assert_tenant_isolated(
        client, object_id=product.pk, list_url=PRODUCTS, detail_url=detail(PRODUCTS, product)
    )
    assert_tenant_isolated(
        client,
        object_id=collection.pk,
        list_url=COLLECTIONS,
        detail_url=detail(COLLECTIONS, collection),
    )
    assert_tenant_isolated(
        client,
        object_id=meta_catalog.pk,
        list_url=META_CATALOGS,
        detail_url=detail(META_CATALOGS, meta_catalog),
    )


@pytest.mark.parametrize(
    ("method", "url_name"),
    [
        ("post", "products"),
        ("patch", "product"),
        ("delete", "product"),
        ("post", "product-image"),
        ("delete", "product-image"),
        ("post", "products-import"),
        ("post", "products-reorder"),
        ("post", "collections"),
        ("patch", "collection"),
        ("delete", "collection"),
        ("post", "collections-reorder"),
        ("post", "meta-catalogs"),
        ("get", "meta-catalogs-available"),
        ("delete", "meta-catalog"),
        ("post", "meta-catalog-sync"),
        ("patch", "meta-catalog-commerce-settings"),
    ],
)
def test_catalog_writes_are_admin_stubs(auth_client, workspace, method, url_name):
    product = ProductFactory(workspace=workspace)
    collection = CollectionFactory(workspace=workspace)
    meta_catalog = MetaCatalogFactory(waba__workspace=workspace)
    urls = {
        "products": PRODUCTS,
        "product": detail(PRODUCTS, product),
        "product-image": detail(PRODUCTS, product, "image/"),
        "products-import": f"{PRODUCTS}import/",
        "products-reorder": f"{PRODUCTS}reorder/",
        "collections": COLLECTIONS,
        "collection": detail(COLLECTIONS, collection),
        "collections-reorder": f"{COLLECTIONS}reorder/",
        "meta-catalogs": META_CATALOGS,
        "meta-catalogs-available": f"{META_CATALOGS}available/",
        "meta-catalog": detail(META_CATALOGS, meta_catalog),
        "meta-catalog-sync": detail(META_CATALOGS, meta_catalog, "sync/"),
        "meta-catalog-commerce-settings": detail(META_CATALOGS, meta_catalog, "commerce-settings/"),
    }
    url = urls[url_name]

    denied = getattr(auth_client(Role.AGENT), method)(url, {}, format="json")
    allowed = getattr(auth_client(Role.ADMIN), method)(url, {}, format="json")

    assert denied.status_code == 403, denied.content
    assert allowed.status_code == 501, allowed.content
    assert allowed.json()["error"]["code"] == "not_implemented"
