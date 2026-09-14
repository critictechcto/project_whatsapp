import pytest

from apps.catalog import demo
from apps.catalog.models import Collection, Product

pytestmark = pytest.mark.django_db


def test_demo_seed_is_idempotent(workspace):
    demo.seed(workspace)
    Product.objects.filter(workspace=workspace, sku="SS-KAJU-KATLI-500").update(name="Edited")
    demo.seed(workspace)

    assert Collection.objects.filter(workspace=workspace).count() == 3
    products = Product.objects.filter(workspace=workspace)
    assert products.count() == 12
    assert products.filter(availability="out_of_stock").count() == 1
    assert products.filter(stock_qty__isnull=False).count() >= 3
    assert not products.filter(collection__isnull=True).exists()
    assert products.get(sku="SS-KAJU-KATLI-500").name == "Edited"
    for product in products:
        assert product.price_paise >= 100
        assert product.sale_price_paise is None or product.sale_price_paise < product.price_paise
