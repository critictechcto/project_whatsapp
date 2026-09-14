"""Catalog model constraints and derived properties."""

import pytest
from django.db import IntegrityError, transaction

from apps.catalog.factories import CollectionFactory, ProductFactory
from apps.catalog.models import Product
from apps.catalog.schema_enums import (
    CATALOG_SYNC_STATUSES,
    META_REVIEW_STATUSES,
    PRODUCT_AVAILABILITIES,
)

pytestmark = pytest.mark.django_db


def test_sku_is_unique_per_workspace(workspace, other_workspace):
    ProductFactory(workspace=workspace, sku="TEE-01")
    ProductFactory(workspace=other_workspace, sku="TEE-01")

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductFactory(workspace=workspace, sku="TEE-01")


def test_collection_names_are_unique_ignoring_case(workspace):
    CollectionFactory(workspace=workspace, name="Sarees")

    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionFactory(workspace=workspace, name="SAREES")


@pytest.mark.parametrize(
    "fields",
    [
        {"price_paise": 99},
        {"price_paise": 1000, "sale_price_paise": 1000},
        {"max_qty_per_order": 0},
        {"max_qty_per_order": 100},
    ],
)
def test_price_and_quantity_checks(workspace, fields):
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductFactory(workspace=workspace, **fields)


def test_effective_price_and_buyer_availability(workspace):
    product = ProductFactory(workspace=workspace, price_paise=50000, sale_price_paise=45000)
    assert product.effective_price_paise == 45000
    assert product.currency == "INR"

    product.stock_qty = 0
    assert product.buyer_availability == Product.Availability.OUT_OF_STOCK
    product.stock_qty = None
    assert product.buyer_availability == Product.Availability.IN_STOCK
    assert not product.is_stock_tracked


def test_model_choices_match_contract_enums():
    assert tuple(Product.Availability.values) == PRODUCT_AVAILABILITIES
    assert tuple(Product.SyncStatus.values) == CATALOG_SYNC_STATUSES
    assert tuple(Product.ReviewStatus.values) == META_REVIEW_STATUSES
