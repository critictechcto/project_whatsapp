"""Payment at booking per service (docs/contracts/booking-payments.md): validation through the
API, the shared ``kind_field_errors`` and the CSV import."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from apps.catalog.factories import ProductFactory
from apps.catalog.models import Product, kind_field_errors

from .conftest import PRODUCTS, detail


def service_body(**overrides) -> dict:
    return {
        "sku": "BRIDAL",
        "kind": "service",
        "name": "Bridal makeup",
        "price_paise": 500000,
        **overrides,
    }


def field_errors(response) -> dict:
    assert response.status_code == 400, response.content
    body = response.json()["error"]
    assert body["code"] == "invalid"
    return body["details"]


# --- kind_field_errors (no database) ---------------------------------------------------------


def errors(kind="service", **kwargs):
    return kind_field_errors(kind, None, None, **kwargs)


def test_defaults_are_valid_for_both_kinds():
    assert errors() == {}
    assert errors("product") == {}


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"booking_payment": "advance"}, "advance_type"),
        ({"booking_payment": "advance", "advance_type": "amount"}, "advance_value"),
        (
            {"booking_payment": "advance", "advance_type": "amount", "advance_value": 99},
            "advance_value",
        ),
        (
            {
                "booking_payment": "advance",
                "advance_type": "amount",
                "advance_value": 50000,
                "effective_price_paise": 50000,
            },
            "advance_value",
        ),
        (
            {"booking_payment": "advance", "advance_type": "percent", "advance_value": 100},
            "advance_value",
        ),
        ({"booking_payment": "full", "advance_type": "percent"}, "advance_type"),
        ({"booking_payment": "store_default", "advance_value": 20}, "advance_value"),
        ({"booking_payment": "later"}, "booking_payment"),
    ],
)
def test_invalid_service_payment_settings(kwargs, field):
    assert field in errors(**kwargs)


def test_valid_advances_and_full():
    assert errors(booking_payment="full") == {}
    assert (
        errors(
            booking_payment="advance",
            advance_type="amount",
            advance_value=49900,
            effective_price_paise=50000,
        )
        == {}
    )
    for percent in (1, 99):
        assert (
            errors(booking_payment="advance", advance_type="percent", advance_value=percent) == {}
        )


def test_products_cannot_ask_for_payment_at_booking():
    assert errors("product", booking_payment="full") == {
        "booking_payment": ["Only services can ask for payment at booking."]
    }


# --- API ---------------------------------------------------------------------------------------

db = pytest.mark.django_db


@db
def test_create_service_with_an_advance(admin):
    response = admin.post(
        PRODUCTS,
        service_body(booking_payment="advance", advance_type="percent", advance_value=20),
        format="json",
    )

    assert response.status_code == 201, response.content
    data = response.json()
    assert (data["booking_payment"], data["advance_type"], data["advance_value"]) == (
        "advance",
        "percent",
        20,
    )


@db
def test_defaults_on_the_api(admin):
    data = admin.post(PRODUCTS, service_body(), format="json").json()

    assert (data["booking_payment"], data["advance_type"], data["advance_value"]) == (
        "store_default",
        "",
        None,
    )


@db
def test_advance_amount_must_be_below_the_effective_price(admin):
    body = service_body(
        sale_price_paise=40000,
        price_paise=50000,
        booking_payment="advance",
        advance_type="amount",
        advance_value=40000,
    )

    assert "advance_value" in field_errors(admin.post(PRODUCTS, body, format="json"))


@db
def test_products_sent_with_an_advance_are_rejected(admin):
    body = {
        "sku": "KAJU",
        "name": "Kaju Katli",
        "price_paise": 64000,
        "booking_payment": "full",
    }

    assert "booking_payment" in field_errors(admin.post(PRODUCTS, body, format="json"))


@db
def test_patch_validates_against_the_stored_values(admin, workspace):
    service = ProductFactory(
        workspace=workspace,
        service=True,
        price_paise=50000,
        booking_payment="advance",
        advance_type="amount",
        advance_value=20000,
    )

    lowered = admin.patch(detail(PRODUCTS, service), {"price_paise": 20000}, format="json")
    assert "advance_value" in field_errors(lowered)

    response = admin.patch(detail(PRODUCTS, service), {"booking_payment": "full"}, format="json")
    assert response.status_code == 200, response.content
    assert (response.json()["advance_type"], response.json()["advance_value"]) == ("", None)


@db
def test_switching_to_a_product_returns_to_the_store_setting(admin, workspace):
    service = ProductFactory(workspace=workspace, service=True, booking_payment="full")

    response = admin.patch(
        detail(PRODUCTS, service), {"kind": "product", "duration_minutes": None}, format="json"
    )

    assert response.status_code == 200, response.content
    assert response.json()["booking_payment"] == "store_default"


@db
def test_database_constraint(workspace):
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductFactory(workspace=workspace, booking_payment="full")


# --- CSV import ---------------------------------------------------------------------------------


def post_csv(client, content: str):
    upload = SimpleUploadedFile("products.csv", content.encode(), content_type="text/csv")
    return client.post(f"{PRODUCTS}import/", {"file": upload}, format="multipart")


@db
def test_import_skips_a_price_below_the_advance(admin, workspace):
    service = ProductFactory(
        workspace=workspace,
        sku="BRIDAL",
        service=True,
        price_paise=50000,
        booking_payment="advance",
        advance_type="amount",
        advance_value=20000,
    )

    response = post_csv(admin, "sku,price\nBRIDAL,150\n")

    assert response.status_code == 200, response.content
    assert response.json()["skipped_count"] == 1
    assert response.json()["errors"][0]["reason"] == "The advance must be less than the price."
    service.refresh_from_db()
    assert service.price_paise == 50000


@db
def test_import_switching_to_a_product_clears_the_advance(admin, workspace):
    service = ProductFactory(
        workspace=workspace,
        sku="BRIDAL",
        service=True,
        booking_payment="advance",
        advance_type="percent",
        advance_value=20,
    )

    response = post_csv(admin, "sku,kind\nBRIDAL,product\n")

    assert response.status_code == 200, response.content
    assert response.json()["updated_count"] == 1
    service.refresh_from_db()
    assert (service.kind, service.booking_payment, service.advance_type) == (
        Product.Kind.PRODUCT,
        "store_default",
        "",
    )
    assert service.advance_value is None
