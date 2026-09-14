"""Product CSV import: upserts by SKU, rupee prices, collections by name and row errors."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.factories import CollectionFactory, MetaCatalogFactory, ProductFactory
from apps.catalog.models import Collection, Product
from common.roles import Role

from .conftest import PRODUCTS

pytestmark = pytest.mark.django_db

IMPORT = f"{PRODUCTS}import/"


def csv_upload(content: str | bytes, name: str = "products.csv"):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return SimpleUploadedFile(name, data, content_type="text/csv")


def post(client, content):
    return client.post(IMPORT, {"file": csv_upload(content)}, format="multipart")


def test_import_creates_and_updates_by_sku(admin, workspace):
    existing = ProductFactory(
        workspace=workspace, sku="KAJU-500", price_paise=50000, stock_qty=3, description="Keep me"
    )
    mithai = CollectionFactory(workspace=workspace, name="Mithai")
    content = (
        "SKU,Name,Price,Sale_Price,Collection,Stock_Qty,Max_Qty_Per_Order,Availability,"
        "Is_Active,Description,Colour\n"
        "KAJU-500,Kaju Katli,640,599.50,mithai,10,5,in_stock,true,,gold\n"
        'BHUJIA-400,Aloo Bhujia,"₹1,110.00",,Namkeen,,,out_of_stock,false,Spicy,\n'
    )

    response = post(admin, content)

    assert response.status_code == 200, response.content
    assert response.json() == {
        "created_count": 1,
        "updated_count": 1,
        "skipped_count": 0,
        "errors": [],
    }
    existing.refresh_from_db()
    assert (existing.name, existing.price_paise, existing.sale_price_paise) == (
        "Kaju Katli",
        64000,
        59950,
    )
    assert existing.collection == mithai
    assert (existing.stock_qty, existing.max_qty_per_order) == (10, 5)
    assert existing.description == "Keep me"

    created = Product.objects.get(workspace=workspace, sku="BHUJIA-400")
    assert created.price_paise == 111000
    assert created.sale_price_paise is None
    assert created.collection.name == "Namkeen"
    assert created.availability == "out_of_stock"
    assert created.is_active is False
    assert created.stock_qty is None
    assert created.max_qty_per_order == 10
    assert created.position > existing.position
    assert Collection.objects.filter(workspace=workspace).count() == 2


def test_import_reports_row_errors(admin, workspace):
    content = "\n".join(
        [
            "sku,name,price,sale_price,availability,is_active,stock_qty",
            ",No sku,100,,,,",
            "bad sku!,Bad,100,,,,",
            "GOOD-1,Good,249.50,,,,",
            "GOOD-1,Duplicate,100,,,,",
            "CHEAP,Cheap,0.99,,,,",
            "FRACTION,Fraction,10.555,,,,",
            "NONAME,,100,,,,",
            "SALE,Sale,100,150,,,",
            "AVAIL,Avail,100,,maybe,,",
            "ACTIVE,Active,100,,,perhaps,",
            "STOCK,Stock,100,,,,-1",
            "",
        ]
    )

    response = post(admin, content)

    assert response.status_code == 200, response.content
    data = response.json()
    assert (data["created_count"], data["updated_count"], data["skipped_count"]) == (1, 0, 10)
    assert [(error["row"], error["sku"]) for error in data["errors"]] == [
        (2, ""),
        (3, "bad sku!"),
        (5, "GOOD-1"),
        (6, "CHEAP"),
        (7, "FRACTION"),
        (8, "NONAME"),
        (9, "SALE"),
        (10, "AVAIL"),
        (11, "ACTIVE"),
        (12, "STOCK"),
    ]
    assert all(error["reason"] for error in data["errors"])
    assert Product.objects.get(workspace=workspace).price_paise == 24950


def test_import_accepts_a_byte_order_mark(admin, workspace):
    response = post(admin, "﻿sku,name,price\nBARFI-1,Barfi,120\n")

    assert response.status_code == 200, response.content
    assert Product.objects.get(workspace=workspace).sku == "BARFI-1"


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        ("name,price\nBarfi,100\n", "No sku column"),
        ("", "empty"),
        ("sku,name,price\n", "no product rows"),
        ("sku,name,price\nKAJU,Café,100\n".encode("latin-1"), "UTF-8"),
        ("sku,name,price\n" + "".join(f"S-{i},N,100\n" for i in range(5001)), "5,000 rows"),
        ("sku,name\n" + "A" * (2 * 1024 * 1024), "2 MB"),
    ],
    ids=["no-sku", "empty", "no-rows", "not-utf8", "too-many-rows", "too-large"],
)
def test_import_rejects_bad_files(admin, workspace, content, fragment):
    response = post(admin, content)

    assert response.status_code == 400, response.content
    [message] = response.json()["error"]["details"]["file"]
    assert fragment in message
    assert not Product.objects.filter(workspace=workspace).exists()


def test_import_queues_a_catalog_sync(admin, workspace, django_capture_on_commit_callbacks):
    MetaCatalogFactory(waba__workspace=workspace)

    with django_capture_on_commit_callbacks() as callbacks:
        assert post(admin, "sku,name,price\nBARFI-1,Barfi,120\n").status_code == 200

    assert len(callbacks) == 1


def test_import_needs_admin(auth_client):
    response = auth_client(Role.AGENT).post(
        IMPORT, {"file": csv_upload("sku\nA\n")}, format="multipart"
    )

    assert response.status_code == 403
