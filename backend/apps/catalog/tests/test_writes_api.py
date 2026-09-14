"""Product and collection writes: validation, ordering, plan gate, isolation and sync queueing."""

import pytest

from apps.catalog.factories import CollectionFactory, MetaCatalogFactory, ProductFactory
from apps.catalog.models import Collection, Product
from common.roles import Role

from .conftest import COLLECTIONS, PRODUCTS, detail

pytestmark = pytest.mark.django_db


def product_body(**overrides) -> dict:
    return {"sku": "KAJU-500", "name": "Kaju Katli (500 g)", "price_paise": 64000, **overrides}


def field_errors(response) -> dict:
    assert response.status_code == 400, response.content
    body = response.json()["error"]
    assert body["code"] == "invalid"
    return body["details"]


# --- Products ---------------------------------------------------------------------------------


def test_create_product(admin, workspace):
    sweets = CollectionFactory(workspace=workspace, name="Mithai")
    ProductFactory(workspace=workspace, position=4)

    response = admin.post(
        PRODUCTS,
        product_body(
            description="Pure ghee",
            sale_price_paise=59900,
            collection_id=str(sweets.pk),
            stock_qty=12,
            max_qty_per_order=5,
            availability="in_stock",
            is_active=True,
        ),
        format="json",
    )

    assert response.status_code == 201, response.content
    data = response.json()
    assert data["sku"] == "KAJU-500"
    assert data["effective_price_paise"] == 59900
    assert data["collection"] == {"id": str(sweets.pk), "name": "Mithai"}
    assert data["stock_qty"] == 12
    assert data["max_qty_per_order"] == 5
    assert data["position"] == 5
    assert data["meta_sync_status"] == "not_synced"
    assert Product.objects.get(pk=data["id"]).workspace == workspace


def test_duplicate_sku_is_a_field_error(admin, workspace, other_workspace):
    ProductFactory(workspace=other_workspace, sku="KAJU-500")
    assert admin.post(PRODUCTS, product_body(), format="json").status_code == 201

    errors = field_errors(admin.post(PRODUCTS, product_body(name="Again"), format="json"))

    assert list(errors) == ["sku"]
    assert Product.objects.filter(workspace=workspace).count() == 1


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"sku": "kaju katli"}, "sku"),
        ({"price_paise": 99}, "price_paise"),
        ({"price_paise": 3_000_000_000}, "price_paise"),
        ({"sale_price_paise": 64000}, "sale_price_paise"),
        ({"max_qty_per_order": 100}, "max_qty_per_order"),
        ({"stock_qty": -1}, "stock_qty"),
        ({"availability": "maybe"}, "availability"),
        ({"name": "x" * 201}, "name"),
    ],
)
def test_create_product_validation(admin, overrides, field):
    errors = field_errors(admin.post(PRODUCTS, product_body(**overrides), format="json"))

    assert field in errors


def test_collection_must_belong_to_the_workspace(admin, other_workspace):
    foreign = CollectionFactory(workspace=other_workspace)

    errors = field_errors(
        admin.post(PRODUCTS, product_body(collection_id=str(foreign.pk)), format="json")
    )

    assert "collection_id" in errors


def test_patch_product(admin, workspace):
    product = ProductFactory(
        workspace=workspace, collection=CollectionFactory(workspace=workspace), stock_qty=5
    )

    response = admin.patch(
        detail(PRODUCTS, product),
        {"name": "Motichoor Laddu", "collection_id": None, "sku": product.sku},
        format="json",
    )

    assert response.status_code == 200, response.content
    product.refresh_from_db()
    assert product.name == "Motichoor Laddu"
    assert product.collection is None
    assert product.stock_qty == 5
    assert response.json()["collection"] is None


def test_sku_is_read_only_after_create(admin, workspace):
    product = ProductFactory(workspace=workspace, sku="OLD-1")

    errors = field_errors(admin.patch(detail(PRODUCTS, product), {"sku": "NEW-1"}, format="json"))

    assert "sku" in errors
    product.refresh_from_db()
    assert product.sku == "OLD-1"


def test_patch_sale_price_is_checked_against_the_stored_price(admin, workspace):
    product = ProductFactory(workspace=workspace, price_paise=20000)

    errors = field_errors(
        admin.patch(detail(PRODUCTS, product), {"sale_price_paise": 20000}, format="json")
    )

    assert "sale_price_paise" in errors


def test_delete_product(admin, workspace):
    product = ProductFactory(workspace=workspace)

    response = admin.delete(detail(PRODUCTS, product))

    assert response.status_code == 204
    assert not Product.objects.filter(pk=product.pk).exists()


def test_deleting_a_synced_product_queues_the_meta_delete(
    admin, workspace, connected, fake_graph, django_capture_on_commit_callbacks
):
    product = ProductFactory(
        workspace=workspace, sku="LADDU-1", meta_sync_status="synced", image="catalog/a.jpg"
    )

    with django_capture_on_commit_callbacks(execute=True):
        assert admin.delete(detail(PRODUCTS, product)).status_code == 204

    [call] = fake_graph.calls_to("batch_catalog_items")
    assert call.kwargs["catalog_id"] == connected.catalog_id
    assert call.kwargs["requests"] == [{"method": "DELETE", "data": {"id": "LADDU-1"}}]


def test_deleting_a_never_synced_product_calls_nothing(
    admin, workspace, connected, fake_graph, django_capture_on_commit_callbacks
):
    product = ProductFactory(workspace=workspace)

    with django_capture_on_commit_callbacks(execute=True):
        assert admin.delete(detail(PRODUCTS, product)).status_code == 204

    assert fake_graph.calls_to("batch_catalog_items") == []


def test_saving_a_product_queues_one_debounced_sync(
    admin, workspace, django_capture_on_commit_callbacks
):
    MetaCatalogFactory(waba__workspace=workspace)
    product = ProductFactory(workspace=workspace)

    with django_capture_on_commit_callbacks() as callbacks:
        admin.patch(detail(PRODUCTS, product), {"name": "Barfi"}, format="json")
        admin.patch(detail(PRODUCTS, product), {"name": "Kaju Barfi"}, format="json")

    assert len(callbacks) == 1


def test_product_writes_are_tenant_isolated(auth_client, workspace, other_workspace):
    product = ProductFactory(workspace=workspace, name="Barfi")
    outsider = auth_client(workspace=other_workspace)

    assert (
        outsider.patch(detail(PRODUCTS, product), {"name": "X"}, format="json").status_code == 404
    )
    assert outsider.delete(detail(PRODUCTS, product)).status_code == 404
    product.refresh_from_db()
    assert product.name == "Barfi"


def test_catalog_writes_need_the_commerce_feature(admin, workspace, no_commerce):
    meta_catalog = MetaCatalogFactory(waba__workspace=workspace)

    response = admin.post(PRODUCTS, product_body(), format="json")

    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "commerce_not_enabled"
    assert admin.post(COLLECTIONS, {"name": "Mithai"}, format="json").status_code == 409
    assert admin.get(PRODUCTS).status_code == 200
    # Disconnecting a Meta catalog stays possible.
    assert admin.delete(f"/api/v1/catalog/meta-catalogs/{meta_catalog.pk}/").status_code == 204


# --- Collections ------------------------------------------------------------------------------


def test_collection_crud(admin, workspace):
    CollectionFactory(workspace=workspace, position=2)

    created = admin.post(COLLECTIONS, {"name": "Mithai", "description": ""}, format="json")
    assert created.status_code == 201, created.content
    data = created.json()
    assert data["position"] == 3
    assert data["product_count"] == 0
    assert data["is_active"] is True

    collection = Collection.objects.get(pk=data["id"])
    ProductFactory(workspace=workspace, collection=collection)
    patched = admin.patch(
        detail(COLLECTIONS, collection), {"name": "MITHAI", "is_active": False}, format="json"
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["name"] == "MITHAI"
    assert patched.json()["product_count"] == 1


def test_collection_names_are_unique_ignoring_case(admin, workspace):
    first = CollectionFactory(workspace=workspace, name="Mithai")
    other = CollectionFactory(workspace=workspace, name="Namkeen")

    assert "name" in field_errors(admin.post(COLLECTIONS, {"name": "mithai"}, format="json"))
    assert "name" in field_errors(
        admin.patch(detail(COLLECTIONS, other), {"name": "MITHAI"}, format="json")
    )
    assert "name" in field_errors(admin.post(COLLECTIONS, {"name": "x" * 25}, format="json"))
    assert first.name == "Mithai"


def test_deleting_a_collection_keeps_its_products(admin, workspace):
    collection = CollectionFactory(workspace=workspace)
    product = ProductFactory(workspace=workspace, collection=collection)

    assert admin.delete(detail(COLLECTIONS, collection)).status_code == 204

    product.refresh_from_db()
    assert product.collection is None


# --- Reordering -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "factory"), [(PRODUCTS, ProductFactory), (COLLECTIONS, CollectionFactory)]
)
def test_reorder_rewrites_positions(admin, workspace, url, factory):
    first = factory(workspace=workspace, position=0, name="Alpha")
    second = factory(workspace=workspace, position=1, name="Bravo")
    third = factory(workspace=workspace, position=7, name="Charlie")

    response = admin.post(f"{url}reorder/", {"ids": [str(third.pk), str(first.pk)]}, format="json")

    assert response.status_code == 204, response.content
    positions = {row.pk: row.position for row in factory._meta.model.objects.all()}
    assert positions == {third.pk: 0, first.pk: 1, second.pk: 2}


@pytest.mark.parametrize(
    ("url", "factory"), [(PRODUCTS, ProductFactory), (COLLECTIONS, CollectionFactory)]
)
def test_reorder_validation(admin, workspace, other_workspace, url, factory):
    mine = factory(workspace=workspace)
    foreign = factory(workspace=other_workspace)

    assert "ids" in field_errors(
        admin.post(f"{url}reorder/", {"ids": [str(mine.pk), str(foreign.pk)]}, format="json")
    )
    assert "ids" in field_errors(
        admin.post(f"{url}reorder/", {"ids": [str(mine.pk), str(mine.pk)]}, format="json")
    )


def test_reorder_needs_admin(auth_client):
    response = auth_client(Role.AGENT).post(f"{PRODUCTS}reorder/", {"ids": []}, format="json")

    assert response.status_code == 403
