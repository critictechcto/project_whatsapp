"""Journey: a seller sets up a welcome message, a price keyword reply and an after-hours notice;
each fires once per message, redeliveries change nothing, and messages the store bot answers never
trigger automations."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from apps.automations.models import AutomationRun

from .conftest import CUSTOMER_WA_ID
from .test_journey_support import Customer, log_in_again, ok, results

pytest_plugins = ["tests.test_journey_support"]
pytestmark = pytest.mark.django_db

IST = ZoneInfo("Asia/Kolkata")
RULES = "/api/v1/automations/rules/"
RUNS = "/api/v1/automations/runs/"
WELCOME = "Namaste! Thanks for writing to Sharma Sweets."
PRICES = "Kaju katli is ₹996/kg and motichoor laddoo ₹640/kg."
CLOSED = "We're closed now and will reply after 9 am."
# Monday to Saturday, 9 am to 9 pm; Sunday closed.
OPEN_HOURS = [{"day": day, "start": "09:00", "end": "21:00"} for day in range(6)]


def texts_to(fake_graph, wa_id: str = CUSTOMER_WA_ID) -> list[str]:
    return [
        m["text"]["body"]
        for m in fake_graph.sent_messages
        if m["to"] == wa_id and m["type"] == "text"
    ]


def test_welcome_keyword_and_after_hours_rules_fire_once(
    seller_api, deliver_meta, fake_graph, time_machine
):
    time_machine.move_to(dt.datetime(2026, 9, 20, 22, 0, tzinfo=IST))  # a Sunday night
    log_in_again(seller_api)
    tag = ok(seller_api.post("/api/v1/contacts/tags/", {"name": "Asked price"}), 201)
    welcome = ok(
        seller_api.post(
            RULES,
            {
                "name": "Welcome",
                "trigger": "first_inbound",
                "priority": 1,
                "actions": [{"type": "send_text", "config": {"text": WELCOME}}],
            },
        ),
        201,
    )
    prices = ok(
        seller_api.post(
            RULES,
            {
                "name": "Prices",
                "trigger": "keyword",
                "keywords": ["price", "rate"],
                "keyword_match": "contains",
                "priority": 2,
                "actions": [
                    {"type": "send_text", "config": {"text": PRICES}},
                    {"type": "add_tags", "config": {"tag_ids": [tag["id"]]}},
                ],
            },
        ),
        201,
    )
    after_hours = ok(
        seller_api.post(
            RULES,
            {
                "name": "After hours",
                "trigger": "outside_business_hours",
                "priority": 3,
                "cooldown_minutes": 120,
                "actions": [{"type": "send_text", "config": {"text": CLOSED}}],
            },
        ),
        201,
    )
    hours = ok(
        seller_api.patch(
            "/api/v1/automations/business-hours/", {"enabled": True, "schedule": OPEN_HOURS}
        )
    )
    assert hours["time_zone"] == "Asia/Kolkata"

    customer = Customer(deliver_meta)
    first = customer.says("Hello, what is the price of kaju katli?")
    assert texts_to(fake_graph) == [WELCOME, PRICES, CLOSED]
    [contact] = results(seller_api.get("/api/v1/contacts/"))
    assert contact["tags"] == [tag["id"]]

    # Meta redelivers the message: no rule runs twice.
    deliver_meta(first)
    assert texts_to(fake_graph) == [WELCOME, PRICES, CLOSED]
    assert AutomationRun.objects.count() == 3

    # Five minutes later: not the first message, prices again, after-hours in cooldown.
    time_machine.move_to(dt.datetime(2026, 9, 20, 22, 5, tzinfo=IST))
    customer.says("And the rate for 2 kg?")
    assert texts_to(fake_graph) == [WELCOME, PRICES, CLOSED, PRICES]
    cooldown = results(seller_api.get(RUNS, {"rule": after_hours["id"], "status": "skipped"}))
    assert len(cooldown) == 1
    assert "Cooldown" in cooldown[0]["detail"]

    # Monday morning inside business hours: nothing fires for a plain message.
    time_machine.move_to(dt.datetime(2026, 9, 21, 10, 0, tzinfo=IST))
    log_in_again(seller_api)
    customer.says("Thank you, I'll come by.")
    assert len(texts_to(fake_graph)) == 4

    by_rule = {r["id"]: r for r in results(seller_api.get(RULES))}
    assert by_rule[welcome["id"]]["run_count"] == 1
    assert by_rule[prices["id"]]["run_count"] == 2
    assert by_rule[after_hours["id"]]["run_count"] == 1
    succeeded = results(seller_api.get(RUNS, {"status": "succeeded", "page_size": 50}))
    assert sorted(r["rule"]["name"] for r in succeeded) == [
        "After hours",
        "Prices",
        "Prices",
        "Welcome",
    ]

    # A second customer gets their own welcome.
    Customer(deliver_meta, wa_id="919812345699", name="Rohan").says("hi there")
    assert texts_to(fake_graph, "919812345699") == [WELCOME]


def test_messages_the_store_bot_claims_skip_automations(
    seller_api, deliver_meta, fake_graph, time_machine
):
    time_machine.move_to(dt.datetime(2026, 9, 20, 22, 0, tzinfo=IST))  # closed
    log_in_again(seller_api)
    ok(
        seller_api.post(
            RULES,
            {
                "name": "Welcome",
                "trigger": "first_inbound",
                "actions": [{"type": "send_text", "config": {"text": WELCOME}}],
            },
        ),
        201,
    )
    ok(
        seller_api.post(
            RULES,
            {
                "name": "Menu keyword",
                "trigger": "keyword",
                "keywords": ["hi", "menu"],
                "keyword_match": "contains",
                "actions": [{"type": "send_text", "config": {"text": PRICES}}],
            },
        ),
        201,
    )
    ok(seller_api.patch("/api/v1/automations/business-hours/", {"enabled": True, "schedule": []}))
    ok(
        seller_api.post(
            RULES,
            {
                "name": "After hours",
                "trigger": "outside_business_hours",
                "actions": [{"type": "send_text", "config": {"text": CLOSED}}],
            },
        ),
        201,
    )
    ok(
        seller_api.post(
            "/api/v1/catalog/products/",
            {"sku": "KAJU-250", "name": "Kaju Katli 250 g", "price_paise": 24900},
        ),
        201,
    )
    store = ok(seller_api.patch("/api/v1/store/settings/", {"enabled": True, "order_prefix": "SS"}))
    assert store["enabled"] is True

    customer = Customer(deliver_meta)
    customer.says("hi")  # a store menu keyword: the bot answers, automations stay out
    assert AutomationRun.objects.count() == 0
    assert texts_to(fake_graph) == []
    menu = fake_graph.sent_messages[-1]
    assert menu["type"] == "interactive"

    customer.taps_template_button("upc:shop:menu", "Menu")  # a well-formed reply id
    assert AutomationRun.objects.count() == 0
    assert texts_to(fake_graph) == []

    # A message the bot doesn't claim still reaches automations (not the first inbound anymore).
    customer.says("Do you deliver on Sundays?")
    assert texts_to(fake_graph) == [CLOSED]
    assert [r["rule"]["name"] for r in results(seller_api.get(RUNS))] == ["After hours"]
