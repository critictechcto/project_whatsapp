"""Journey: roles and plans. A viewer reads every area but can't change anything; the Starter plan
refuses scheduling and keyword automations; a halted subscription keeps data readable but adds
nothing new."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.automations.models import AutomationRun
from apps.billing.models import Subscription

from .test_journey_support import Customer, approved_template, error, invite_and_join, ok, results

pytest_plugins = ["tests.test_journey_support"]
pytestmark = pytest.mark.django_db

RULES = "/api/v1/automations/rules/"
KEYWORD_RULE = {
    "name": "Prices",
    "trigger": "keyword",
    "keywords": ["price"],
    "keyword_match": "contains",
    "actions": [{"type": "send_text", "config": {"text": "Kaju katli is ₹996/kg."}}],
}


def set_subscription(api, **fields) -> None:
    """Plan changes go through Razorpay checkout; tests set the outcome directly."""
    Subscription.objects.filter(workspace_id=api.workspace_id).update(**fields)


def campaign_draft(api, number_id, template_id, contact_id) -> dict:
    return ok(
        api.post(
            "/api/v1/campaigns/",
            {
                "name": "Weekend offer",
                "template_id": template_id,
                "phone_number_id": number_id,
                "audience": {"tag_ids": [], "match": "any", "contact_ids": [contact_id]},
                "variable_mapping": {
                    "body": [{"source": "contact_field", "value": "name", "fallback": "there"}],
                    "header": None,
                    "buttons": {},
                },
            },
        ),
        201,
    )


def test_a_viewer_reads_every_area_but_writes_nothing(seller_api, run_on_commit, fake_graph):
    viewer = invite_and_join(
        seller_api, run_on_commit, email="audit@sharmasweets.in", full_name="Audit", role="viewer"
    )
    agent = invite_and_join(
        seller_api, run_on_commit, email="meera@sharmasweets.in", full_name="Meera", role="agent"
    )
    [waba] = results(seller_api.get("/api/v1/whatsapp/accounts/"))
    contact = ok(
        seller_api.post("/api/v1/contacts/", {"name": "Priya", "phone_e164": "+919876543210"}), 201
    )
    product = ok(
        seller_api.post(
            "/api/v1/catalog/products/",
            {"sku": "KAJU-250", "name": "Kaju Katli 250 g", "price_paise": 24900},
        ),
        201,
    )

    readable = [
        "/api/v1/auth/me/",
        "/api/v1/workspaces/members/",
        "/api/v1/whatsapp/accounts/",
        "/api/v1/whatsapp/phone-numbers/",
        "/api/v1/templates/",
        "/api/v1/contacts/",
        f"/api/v1/contacts/{contact['id']}/",
        "/api/v1/contacts/tags/",
        "/api/v1/inbox/conversations/",
        "/api/v1/campaigns/",
        RULES,
        "/api/v1/automations/runs/",
        "/api/v1/automations/business-hours/",
        "/api/v1/billing/subscription/",
        "/api/v1/billing/usage/",
        "/api/v1/catalog/products/",
        "/api/v1/catalog/collections/",
        "/api/v1/orders/",
        "/api/v1/store/settings/",
        "/api/v1/seller-alerts/recipients/",
    ]
    for url in readable:
        assert viewer.get(url).status_code == 200, url

    writes = [
        ("post", "/api/v1/workspaces/invitations/", {"email": "x@y.in", "role": "agent"}),
        ("post", "/api/v1/whatsapp/embedded-signup/", {"code": "c", "waba_id": "1"}),
        ("post", "/api/v1/templates/", {"waba": waba["id"], "name": "t", "language": "en"}),
        ("post", "/api/v1/contacts/", {"name": "Arjun", "phone_e164": "+919812345601"}),
        ("patch", f"/api/v1/contacts/{contact['id']}/", {"name": "Priya S"}),
        ("post", "/api/v1/contacts/tags/", {"name": "VIP"}),
        ("post", "/api/v1/campaigns/", {"name": "Offer"}),
        ("post", RULES, KEYWORD_RULE),
        ("patch", "/api/v1/automations/business-hours/", {"enabled": True}),
        ("post", "/api/v1/catalog/products/", {"sku": "LADDOO", "name": "Laddoo"}),
        ("patch", f"/api/v1/catalog/products/{product['id']}/", {"name": "Kaju"}),
        ("patch", "/api/v1/store/settings/", {"enabled": True}),
        ("patch", "/api/v1/payments/account/", {"provider": "razorpay"}),
        ("post", "/api/v1/seller-alerts/recipients/", {"name": "R", "phone_e164": "+9197"}),
        ("post", "/api/v1/billing/subscription/cancel/", None),
    ]
    for method, url, body in writes:
        error(getattr(viewer, method)(url, body), 403, "insufficient_role")
    ok(viewer.post("/api/v1/inbox/ws-ticket/"))  # the live inbox is open to every member

    # Agents handle chats and contacts, not the store's setup or campaigns.
    ok(agent.patch(f"/api/v1/contacts/{contact['id']}/", {"name": "Priya Sharma"}))
    error(agent.post("/api/v1/campaigns/", {"name": "Offer"}), 403, "insufficient_role")
    error(agent.patch("/api/v1/store/settings/", {"enabled": True}), 403, "insufficient_role")
    error(agent.get("/api/v1/payments/account/"), 403, "insufficient_role")

    assert ok(seller_api.get(f"/api/v1/contacts/{contact['id']}/"))["name"] == "Priya Sharma"
    assert ok(seller_api.get("/api/v1/store/settings/"))["enabled"] is False
    assert len(results(seller_api.get("/api/v1/contacts/"))) == 1


def test_starter_refuses_scheduling_and_keyword_rules(
    seller_api, seller_number_id, deliver_meta, fake_graph
):
    template = approved_template(
        seller_api, deliver_meta, name="weekend_offer", body="Hi {{1}}, 10% off this weekend."
    )
    contact = ok(
        seller_api.post(
            "/api/v1/contacts/",
            {
                "name": "Priya",
                "phone_e164": "+919876543210",
            },
        ),
        201,
    )

    # During the Growth trial: a keyword rule and a scheduled campaign are fine.
    trial_rule = ok(seller_api.post(RULES, KEYWORD_RULE), 201)
    later = (timezone.now() + timedelta(hours=2)).isoformat()
    scheduled = campaign_draft(seller_api, seller_number_id, template["id"], contact["id"])
    launched = seller_api.post(
        f"/api/v1/campaigns/{scheduled['id']}/launch/",
        {"consent_attested": True, "scheduled_at": later},
    )
    assert ok(launched)["status"] == "scheduled"

    # The seller moves to Starter.
    set_subscription(seller_api, plan_id="starter", status="active")
    plan = ok(seller_api.get("/api/v1/billing/subscription/"))["plan"]
    assert plan["id"] == "starter"

    draft = campaign_draft(seller_api, seller_number_id, template["id"], contact["id"])
    url = f"/api/v1/campaigns/{draft['id']}/"
    error(
        seller_api.post(f"{url}launch/", {"consent_attested": True, "scheduled_at": later}),
        409,
        "feature_not_available",
    )
    assert ok(seller_api.get(url))["status"] == "draft"
    # Sending now is on every plan.
    assert ok(seller_api.post(f"{url}launch/", {"consent_attested": True}))["status"] in (
        "running",
        "completed",
    )

    error(seller_api.post(RULES, {**KEYWORD_RULE, "name": "Rates"}), 409, "feature_not_available")
    paused = ok(seller_api.post(RULES, {**KEYWORD_RULE, "name": "Rates", "is_active": False}), 201)
    error(
        seller_api.patch(f"{RULES}{paused['id']}/", {"is_active": True}),
        409,
        "feature_not_available",
    )
    welcome = {
        "name": "Welcome",
        "trigger": "first_inbound",
        "actions": [{"type": "send_text", "config": {"text": "Namaste!"}}],
    }
    ok(seller_api.post(RULES, welcome), 201)

    # The keyword rule made during the trial stays but doesn't run on Starter.
    Customer(deliver_meta).says("what is the price?")
    [skipped] = AutomationRun.objects.filter(rule_id=trial_rule["id"])
    assert skipped.status == "skipped"
    assert "not included" in skipped.detail
    texts = [m["text"]["body"] for m in fake_graph.sent_messages if m["type"] == "text"]
    assert texts == ["Namaste!"]


def test_a_halted_subscription_keeps_data_but_adds_nothing(
    seller_api, seller_number_id, run_on_commit, deliver_meta, fake_graph
):
    ok(seller_api.post("/api/v1/contacts/", {"name": "Priya", "phone_e164": "+919876543210"}), 201)
    ok(
        seller_api.post(
            "/api/v1/catalog/products/",
            {"sku": "KAJU-250", "name": "Kaju Katli 250 g", "price_paise": 24900},
        ),
        201,
    )

    set_subscription(seller_api, status="halted")
    subscription = ok(seller_api.get("/api/v1/billing/subscription/"))
    assert subscription["status"] == "halted"
    usage = {m["key"]: m for m in ok(seller_api.get("/api/v1/billing/usage/"))["metrics"]}
    assert {k: (m["used"], m["limit"]) for k, m in usage.items()} == {
        "whatsapp_numbers": (1, 1),
        "members": (1, 1),
        "contacts": (1, 1),
    }

    details = error(
        seller_api.post("/api/v1/contacts/", {"name": "Arjun", "phone_e164": "+919812345601"}),
        409,
        "quota_exceeded",
    )["details"]
    assert details == {"metric": "contacts", "limit": 1, "used": 1}
    error(
        seller_api.post(
            "/api/v1/workspaces/invitations/", {"email": "meera@sharmasweets.in", "role": "agent"}
        ),
        409,
        "quota_exceeded",
    )
    error(seller_api.post(RULES, KEYWORD_RULE), 409, "feature_not_available")
    error(
        seller_api.post(
            "/api/v1/catalog/products/",
            {"sku": "LADDOO-500", "name": "Motichoor Laddoo 500 g", "price_paise": 32000},
        ),
        409,
        "commerce_not_enabled",
    )

    # Everything already there stays readable, and customers can still write in.
    assert len(results(seller_api.get("/api/v1/contacts/"))) == 1
    assert len(results(seller_api.get("/api/v1/catalog/products/"))) == 1
    Customer(deliver_meta, wa_id="919812345699", name="Rohan").says("Hello?")
    assert len(results(seller_api.get("/api/v1/contacts/"))) == 2
    [conversation] = results(seller_api.get("/api/v1/inbox/conversations/"))
    assert conversation["contact"]["phone_e164"] == "+919812345699"
