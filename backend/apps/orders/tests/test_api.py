"""Orders and store API: the implemented reads, role gates, stubs and tenant isolation."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.orders.factories import (
    OrderEventFactory,
    OrderFactory,
    OrderItemFactory,
    StoreSettingsFactory,
)
from apps.orders.models import Order, StoreSettings
from apps.payments.factories import PaymentLinkFactory
from apps.whatsapp.factories import PhoneNumberFactory
from common.roles import Role
from common.testing import assert_tenant_isolated, result_ids

pytestmark = pytest.mark.django_db

ORDERS = "/api/v1/orders/"
STORE = "/api/v1/store/"


def order_url(order, suffix: str = "") -> str:
    return f"{ORDERS}{order.pk}/{suffix}"


def error_code(response) -> str:
    return response.json()["error"]["code"]


# --- Orders list and detail -----------------------------------------------------------------


def test_list_is_newest_first_and_hides_drafts(auth_client, workspace):
    older = OrderFactory(workspace=workspace)
    newer = OrderFactory(workspace=workspace, status="pending_payment")
    draft = OrderFactory(workspace=workspace, status="draft")
    Order.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(hours=1))

    response = auth_client(Role.VIEWER).get(ORDERS)

    assert response.status_code == 200, response.content
    ids = [item["id"] for item in response.json()["results"]]
    assert ids == [str(newer.pk), str(older.pk)]
    assert str(draft.pk) not in ids

    drafts = auth_client(Role.VIEWER).get(ORDERS, {"status": "draft,confirmed"})
    assert result_ids(drafts) == {str(draft.pk), str(older.pk)}


def test_list_item_shape(auth_client, workspace):
    order = OrderFactory(workspace=workspace, payment_method="", payment_status="unpaid")

    item = auth_client(Role.VIEWER).get(ORDERS).json()["results"][0]

    assert item == {
        "id": str(order.pk),
        "number": order.number,
        "status": "confirmed",
        "payment_status": "unpaid",
        "payment_method": None,
        "source": "bot",
        "contact": {
            "id": str(order.contact.pk),
            "name": order.contact.name,
            "phone_e164": order.contact.phone_e164,
            "marketing_opt_in_status": order.contact.marketing_opt_in_status,
        },
        "total_paise": order.total_paise,
        "item_count": order.item_count,
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }


def test_list_filters(auth_client, workspace):
    shipped_cod = OrderFactory(
        workspace=workspace, status="shipped", payment_method="cod", payment_status="cod_pending"
    )
    delivered = OrderFactory(workspace=workspace, status="delivered", number="SS-7777")
    checkout = OrderFactory(workspace=workspace, status="awaiting_address", payment_status="unpaid")
    client = auth_client(Role.VIEWER)

    assert result_ids(client.get(ORDERS, {"stage": "open"})) == {str(shipped_cod.pk)}
    assert result_ids(client.get(ORDERS, {"stage": "closed"})) == {str(delivered.pk)}
    assert result_ids(client.get(ORDERS, {"stage": "checkout"})) == {str(checkout.pk)}
    assert result_ids(client.get(ORDERS, {"payment_method": "cod"})) == {str(shipped_cod.pk)}
    assert result_ids(client.get(ORDERS, {"payment_status": "unpaid"})) == {str(checkout.pk)}
    assert result_ids(client.get(ORDERS, {"search": "7777"})) == {str(delivered.pk)}
    assert result_ids(client.get(ORDERS, {"search": shipped_cod.contact.phone_e164[-6:]})) == {
        str(shipped_cod.pk)
    }
    assert result_ids(client.get(ORDERS, {"contact": str(checkout.contact_id)})) == {
        str(checkout.pk)
    }
    tomorrow = (timezone.now() + timedelta(days=1)).date().isoformat()
    assert result_ids(client.get(ORDERS, {"created_after": tomorrow})) == set()
    assert len(result_ids(client.get(ORDERS, {"created_before": tomorrow}))) == 3


@pytest.mark.parametrize(
    "params",
    [
        {"status": "lost"},
        {"stage": "later"},
        {"payment_status": "free"},
        {"contact": "not-a-uuid"},
        {"created_after": "yesterday"},
    ],
)
def test_list_rejects_bad_filters(auth_client, workspace, params):
    response = auth_client(Role.VIEWER).get(ORDERS, params)

    assert response.status_code == 400, response.content


def test_detail_shape(auth_client, workspace):
    order = OrderFactory(workspace=workspace, status="confirmed", notes="Gift wrap")
    OrderItemFactory(order=order, position=1, sku="B", image_url="")
    first = OrderItemFactory(order=order, position=0, sku="A")
    PaymentLinkFactory(order=order, reference_id="SS-1-1", status="expired")
    latest = PaymentLinkFactory(order=order, reference_id="SS-1-2", status="paid")

    response = auth_client(Role.VIEWER).get(order_url(order))

    assert response.status_code == 200, response.content
    data = response.json()
    assert [item["sku"] for item in data["items"]] == ["A", "B"]
    assert data["items"][0]["product_id"] == (str(first.product_id) if first.product_id else None)
    assert data["items"][1]["image_url"] is None
    assert data["payment_link"]["id"] == str(latest.pk)
    assert data["payment_link"]["status"] == "paid"
    assert data["phone_number"]["id"] == str(order.phone_number_id)
    assert data["address"]["pincode"] == order.address["pincode"]
    assert data["allowed_transitions"] == ["packed", "shipped", "cancelled"]
    assert data["notes"] == "Gift wrap"
    assert data["courier_name"] == ""
    assert data["conversation_id"] is None


def test_detail_without_payment_link_or_address(auth_client, workspace):
    order = OrderFactory(workspace=workspace, address=None, payment_method="cod")

    data = auth_client(Role.VIEWER).get(order_url(order)).json()

    assert data["payment_link"] is None
    assert data["address"] is None


def test_events_are_oldest_first(auth_client, workspace):
    order = OrderFactory(workspace=workspace)
    user = UserFactory()
    first = OrderEventFactory(order=order, type="created")
    second = OrderEventFactory(
        order=order,
        type="status_changed",
        from_status="confirmed",
        to_status="packed",
        actor="dashboard",
        user=user,
    )
    OrderEventFactory(order=OrderFactory(workspace=workspace))

    response = auth_client(Role.VIEWER).get(order_url(order, "events/"))

    assert response.status_code == 200, response.content
    results = response.json()["results"]
    assert [event["id"] for event in results] == [str(first.pk), str(second.pk)]
    assert results[1]["user"]["id"] == str(user.pk)
    assert results[1]["from_status"] == "confirmed"
    assert results[0]["message_id"] is None


def test_summary(auth_client, workspace, other_workspace):
    OrderFactory(workspace=workspace, status="confirmed", total_paise=10000)
    OrderFactory(workspace=workspace, status="needs_attention", total_paise=5000)
    OrderFactory(workspace=workspace, status="pending_payment", total_paise=7000)
    OrderFactory(workspace=workspace, status="cancelled", total_paise=9000)
    yesterday = OrderFactory(workspace=workspace, status="delivered", total_paise=3000)
    Order.objects.filter(pk=yesterday.pk).update(created_at=timezone.now() - timedelta(days=2))
    OrderFactory(workspace=other_workspace, status="confirmed", total_paise=99999)

    response = auth_client(Role.VIEWER).get(f"{ORDERS}summary/")

    assert response.status_code == 200, response.content
    assert response.json() == {
        "today_count": 2,
        "today_revenue_paise": 15000,
        "open_count": 2,
        "needs_attention_count": 1,
        "awaiting_payment_count": 1,
    }


def test_orders_are_tenant_isolated(auth_client, workspace, other_workspace):
    order = OrderFactory(workspace=workspace)
    client = auth_client(workspace=other_workspace)

    assert_tenant_isolated(client, object_id=order.pk, list_url=ORDERS, detail_url=order_url(order))
    assert client.get(order_url(order, "events/")).status_code == 404
    assert client.post(order_url(order, "cancel/"), {}, format="json").status_code == 404


@pytest.mark.parametrize(
    ("method", "suffix", "role"),
    [
        ("patch", "", Role.AGENT),
        ("post", "transition/", Role.AGENT),
        ("post", "cancel/", Role.AGENT),
        ("post", "mark-cod-collected/", Role.AGENT),
        ("post", "mark-refunded/", Role.ADMIN),
    ],
)
def test_order_actions_are_role_gated_stubs(auth_client, workspace, method, suffix, role):
    order = OrderFactory(workspace=workspace)
    below = Role.VIEWER if role == Role.AGENT else Role.AGENT

    denied = getattr(auth_client(below), method)(order_url(order, suffix), {}, format="json")
    allowed = getattr(auth_client(role), method)(order_url(order, suffix), {}, format="json")

    assert denied.status_code == 403, denied.content
    assert allowed.status_code == 501, allowed.content
    assert error_code(allowed) == "not_implemented"


def test_unknown_order_is_404_before_the_stub(auth_client, workspace):
    response = auth_client(Role.ADMIN).post(
        f"{ORDERS}00000000-0000-0000-0000-000000000000/cancel/", {}, format="json"
    )

    assert response.status_code == 404


# --- Store ----------------------------------------------------------------------------------


def test_store_settings_are_created_on_first_read(auth_client, workspace):
    workspace.name = "Sharma Sweets"
    workspace.save(update_fields=["name"])
    number = PhoneNumberFactory(
        workspace=workspace,
        waba__workspace=workspace,
        is_default=True,
        display_phone_number="+91 98000 12345",
    )

    response = auth_client(Role.VIEWER).get(f"{STORE}settings/")

    assert response.status_code == 200, response.content
    data = response.json()
    assert StoreSettings.objects.filter(workspace=workspace).count() == 1
    assert data["store_name"] == "Sharma Sweets"
    assert data["order_prefix"] == "SS"
    assert data["enabled"] is False
    assert data["shop_mode"] == "bot"
    assert data["menu_keywords"] == ["hi", "hello", "menu", "shop", "start"]
    assert data["phone_number_id"] is None
    assert data["store_link"] == "https://wa.me/919800012345?text=Hi"
    assert data["notification_templates"] == {
        "confirmed": None,
        "packed": None,
        "shipped": None,
        "delivered": None,
        "cancelled": None,
        "payment_reminder": None,
    }
    assert number.workspace_id == workspace.pk


def test_store_settings_are_per_workspace(auth_client, workspace, other_workspace):
    StoreSettingsFactory(workspace=workspace, store_name="Mine")

    response = auth_client(workspace=other_workspace).get(f"{STORE}settings/")

    assert response.status_code == 200
    assert response.json()["store_name"] != "Mine"


@pytest.mark.parametrize(
    ("method", "path", "role"),
    [
        ("patch", "settings/", Role.ADMIN),
        ("post", "starter-templates/", Role.ADMIN),
    ],
)
def test_store_writes_are_admin_stubs(auth_client, workspace, method, path, role):
    denied = getattr(auth_client(Role.AGENT), method)(f"{STORE}{path}", {}, format="json")
    allowed = getattr(auth_client(role), method)(f"{STORE}{path}", {}, format="json")

    assert denied.status_code == 403, denied.content
    assert allowed.status_code == 501, allowed.content


def test_checklist_is_a_viewer_stub(auth_client, workspace):
    response = auth_client(Role.VIEWER).get(f"{STORE}checklist/")

    assert response.status_code == 501
    assert error_code(response) == "not_implemented"


def test_store_requires_membership(api_client, other_workspace, auth_client):
    response = auth_client(Role.VIEWER).get(f"{STORE}settings/")
    assert response.status_code == 200
    assert api_client.get(f"{STORE}settings/").status_code == 401
