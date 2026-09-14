"""Store settings changes, the setup checklist and starter templates."""

import json

import pytest
from django.apps import apps as django_apps

from apps.billing import entitlements
from apps.catalog.factories import MetaCatalogFactory, ProductFactory
from apps.message_templates.factories import MessageTemplateFactory, standard_components
from apps.message_templates.models import MessageTemplate
from apps.orders.factories import StoreSettingsFactory
from apps.orders.models import StoreSettings
from apps.orders.store_setup import CHECKLIST_NOTIFICATIONS, STARTER_TEMPLATES
from apps.payments.factories import PaymentAccountFactory
from apps.whatsapp.factories import PhoneNumberFactory, WhatsAppBusinessAccountFactory
from common.roles import Role

pytestmark = pytest.mark.django_db

STORE = "/api/v1/store/"
CHECKLIST_KEYS = [
    "whatsapp_connected",
    "products_added",
    "payments_configured",
    "order_templates_ready",
    "alert_number_verified",
    "store_enabled",
]
CONFIRMED_BODY = "Hi {{1}}, order {{2}} for {{3}} is confirmed ({{4}}). Thank you!"


def error(response) -> dict:
    return response.json()["error"]


def patch(auth_client, data):
    return auth_client(Role.ADMIN).patch(f"{STORE}settings/", data, format="json")


def checklist(auth_client, role=Role.VIEWER) -> dict[str, dict]:
    response = auth_client(role).get(f"{STORE}checklist/")
    assert response.status_code == 200, response.content
    items = response.json()["items"]
    assert [item["key"] for item in items] == CHECKLIST_KEYS
    return {item["key"]: item for item in items}


# --- Settings -----------------------------------------------------------------------------------


def test_enabling_names_what_is_missing(auth_client, workspace):
    response = patch(auth_client, {"enabled": True})

    assert response.status_code == 409, response.content
    assert error(response)["code"] == "commerce_not_enabled"
    message = error(response)["message"]
    assert "active product" in message
    assert "connected WhatsApp number" in message
    assert "plan" not in message
    assert not StoreSettings.objects.filter(workspace=workspace, enabled=True).exists()


def test_enabling_needs_the_commerce_feature(auth_client, workspace, number, monkeypatch):
    ProductFactory(workspace=workspace)
    monkeypatch.setattr(entitlements, "has_feature", lambda workspace, feature: False)

    response = patch(auth_client, {"enabled": True})

    assert response.status_code == 409
    assert "plan" in error(response)["message"]


def test_enabling_with_a_product_and_a_connected_number(auth_client, workspace, number):
    ProductFactory(workspace=workspace)

    response = patch(auth_client, {"enabled": True, "store_name": "  Sharma Sweets "})

    assert response.status_code == 200, response.content
    assert response.json()["enabled"] is True
    assert response.json()["store_name"] == "Sharma Sweets"


def test_patch_normalises_lists_and_validates_fields(auth_client, workspace):
    response = patch(
        auth_client,
        {
            "menu_keywords": [" Hi", "MENU", "hi"],
            "serviceable_pincodes": ["411001", "411001", "560034"],
            "order_prefix": "SWT",
            "cod_enabled": True,
            "cod_fee_paise": 2000,
            "free_shipping_above_paise": None,
        },
    )
    invalid = patch(auth_client, {"order_prefix": "s1", "serviceable_pincodes": ["4110"]})

    assert response.status_code == 200, response.content
    data = response.json()
    assert data["menu_keywords"] == ["hi", "menu"]
    assert data["serviceable_pincodes"] == ["411001", "560034"]
    assert (data["order_prefix"], data["cod_enabled"], data["cod_fee_paise"]) == ("SWT", True, 2000)
    assert invalid.status_code == 400
    assert StoreSettings.objects.get(workspace=workspace).order_prefix == "SWT"


def test_store_number_must_belong_to_the_workspace(auth_client, workspace, other_workspace):
    foreign = PhoneNumberFactory(workspace=other_workspace, waba__workspace=other_workspace)
    own = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)

    refused = patch(auth_client, {"phone_number_id": str(foreign.pk)})
    accepted = patch(auth_client, {"phone_number_id": str(own.pk)})

    assert refused.status_code == 400
    assert "phone_number_id" in json.dumps(error(refused)["details"])
    assert accepted.status_code == 200, accepted.content
    assert accepted.json()["phone_number_id"] == str(own.pk)


def test_notification_templates_are_checked(auth_client, workspace, number):
    confirmed = MessageTemplateFactory(
        waba=number.waba, components=standard_components(CONFIRMED_BODY)
    )
    too_few = MessageTemplateFactory(
        waba=number.waba, components=standard_components("Hi {{1}}, thanks.")
    )
    foreign = MessageTemplateFactory(
        waba=WhatsAppBusinessAccountFactory(), components=standard_components(CONFIRMED_BODY)
    )

    mapped = patch(auth_client, {"notification_templates": {"confirmed": str(confirmed.pk)}})
    refused = patch(
        auth_client,
        {"notification_templates": {"packed": str(too_few.pk), "cancelled": str(foreign.pk)}},
    )
    cleared = patch(auth_client, {"notification_templates": {"confirmed": None}})

    assert mapped.status_code == 200, mapped.content
    assert mapped.json()["notification_templates"]["confirmed"] == str(confirmed.pk)
    assert mapped.json()["notification_templates"]["packed"] is None
    assert refused.status_code == 400
    details = json.dumps(error(refused)["details"])
    assert "packed" in details
    assert "cancelled" in details
    assert cleared.json()["notification_templates"]["confirmed"] is None


def test_native_catalog_mode_needs_a_connected_catalog(auth_client, workspace, number):
    refused = patch(auth_client, {"shop_mode": "native_catalog"})
    MetaCatalogFactory(waba=number.waba)
    accepted = patch(auth_client, {"shop_mode": "native_catalog"})

    assert refused.status_code == 409
    assert error(refused)["code"] == "catalog_not_connected"
    assert accepted.status_code == 200, accepted.content
    assert accepted.json()["shop_mode"] == "native_catalog"


# --- Checklist ----------------------------------------------------------------------------------


def test_checklist_starts_with_nothing_done(auth_client, workspace):
    items = checklist(auth_client)

    assert not any(item["done"] for item in items.values())
    assert all(item["detail"] for item in items.values())


def test_checklist_reflects_a_finished_setup(auth_client, workspace, number):
    ProductFactory(workspace=workspace)
    templates = {
        f"{key}_template": MessageTemplateFactory(
            waba=number.waba, name=f"order_{key}", status=MessageTemplate.Status.APPROVED
        )
        for key in CHECKLIST_NOTIFICATIONS
    }
    StoreSettingsFactory(workspace=workspace, enabled=True, cod_enabled=True, **templates)
    alert_recipient = django_apps.get_model("seller_alerts", "AlertRecipient")
    alert_recipient.objects.create(
        workspace=workspace,
        name="Owner",
        phone_e164="+919800000001",
        wa_id="919800000001",
        status="verified",
    )

    items = checklist(auth_client)

    assert all(item["done"] for item in items.values()), items


def test_payments_are_configured_by_a_verified_gateway(auth_client, workspace):
    PaymentAccountFactory(workspace=workspace)

    assert checklist(auth_client)["payments_configured"]["done"] is True


def test_order_templates_need_approval(auth_client, workspace, number):
    templates = {
        f"{key}_template": MessageTemplateFactory(waba=number.waba, name=f"order_{key}")
        for key in CHECKLIST_NOTIFICATIONS
    }
    StoreSettingsFactory(workspace=workspace, **templates)

    item = checklist(auth_client)["order_templates_ready"]

    assert item["done"] is False
    assert "0 of 5" in item["detail"]


# --- Starter templates --------------------------------------------------------------------------


def test_starter_templates_need_a_connected_store_number(auth_client, workspace):
    response = auth_client(Role.ADMIN).post(f"{STORE}starter-templates/", format="json")

    assert response.status_code == 409
    assert error(response)["code"] == "whatsapp_not_connected"


def test_starter_templates_are_created_submitted_and_mapped(auth_client, workspace, number):
    names = [starter.name for starter in STARTER_TEMPLATES]
    confirmed = MessageTemplateFactory(
        waba=number.waba,
        status=MessageTemplate.Status.APPROVED,
        components=standard_components(CONFIRMED_BODY),
    )
    StoreSettingsFactory(workspace=workspace, confirmed_template=confirmed)
    client = auth_client(Role.ADMIN)

    response = client.post(f"{STORE}starter-templates/", format="json")

    assert response.status_code == 200, response.content
    assert response.json() == {"created": names, "existing": []}
    created = MessageTemplate.objects.filter(waba=number.waba, name__in=names)
    assert created.count() == 6
    assert set(created.values_list("status", flat=True)) == {MessageTemplate.Status.PENDING}
    assert set(created.values_list("category", flat=True)) == {"UTILITY"}
    store = StoreSettings.objects.get(workspace=workspace)
    assert store.confirmed_template_id == confirmed.pk
    assert store.shipped_template.name == "upc_order_shipped"
    assert store.payment_reminder_template.name == "upc_payment_reminder"

    again = client.post(f"{STORE}starter-templates/", format="json")

    assert again.json() == {"created": [], "existing": names}
    assert MessageTemplate.objects.filter(waba=number.waba, name__in=names).count() == 6
