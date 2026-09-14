"""Rule evaluation, guards, actions and failure handling for inbound messages."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.automations import engine
from apps.automations.engine import MAX_AUTOMATED_SENDS_PER_HOUR, process_inbound
from apps.automations.factories import AutomationRuleFactory, BusinessHoursFactory
from apps.automations.models import AutomationRule, AutomationRun
from apps.billing import entitlements
from apps.contacts.factories import TagFactory
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import Conversation, Message
from apps.message_templates.models import MessageTemplate
from apps.tenants.factories import MembershipFactory
from apps.whatsapp.factories import PhoneNumberFactory
from common.roles import Role

pytestmark = pytest.mark.django_db

IST = ZoneInfo("Asia/Kolkata")
PRICE_REPLY = "Our prices start at ₹499."
CLOSE = {"type": "close_conversation", "config": {}}


def text_action(text: str = PRICE_REPLY) -> dict:
    return {"type": "send_text", "config": {"text": text}}


def template_action(template, *params: dict) -> dict:
    return {
        "type": "send_template",
        "config": {"template_id": str(template.pk), "body_params": list(params)},
    }


def make_rule(workspace, **kwargs) -> AutomationRule:
    return AutomationRuleFactory(workspace=workspace, **kwargs)


def automation_messages(conversation):
    return Message.objects.filter(
        conversation=conversation, source=Message.Source.AUTOMATION
    ).order_by("created_at")


def outcomes(runs) -> list[tuple]:
    return [(run.rule_id, run.status) for run in runs]


def action_outcomes(run) -> list[tuple]:
    return [(result["status"], result.get("code")) for result in run.action_results]


# --- Keyword rules and replies ------------------------------------------------------------------


def test_keyword_rule_queues_an_automation_reply(workspace, conversation, inbound):
    rule = make_rule(workspace)
    message = inbound("PRICE")

    runs = process_inbound(message.pk)

    assert outcomes(runs) == [(rule.pk, "succeeded")]
    reply = automation_messages(conversation).get()
    assert (reply.direction, reply.status, reply.type) == ("outbound", "queued", "text")
    assert reply.text == PRICE_REPLY
    assert reply.source_ref == str(rule.pk)
    assert reply.idempotency_key == f"automation:{rule.pk}:{message.wamid}:0"
    assert runs[0].detail == "Ran 1 action(s)."
    assert runs[0].action_results == [
        {"index": 0, "type": "send_text", "status": "succeeded", "message_id": str(reply.pk)}
    ]
    assert (runs[0].conversation_id, runs[0].message_id) == (conversation.pk, message.pk)
    rule.refresh_from_db()
    assert rule.run_count == 1
    assert rule.last_triggered_at is not None


def test_reprocessing_a_message_is_idempotent(workspace, conversation, inbound):
    rule = make_rule(workspace)
    message = inbound("price")

    first = process_inbound(message.pk)
    second = process_inbound(message.pk)

    assert [run.pk for run in second] == [run.pk for run in first]
    assert AutomationRun.objects.count() == 1
    assert automation_messages(conversation).count() == 1
    rule.refresh_from_db()
    assert rule.run_count == 1


def test_exact_and_contains_keywords(workspace, inbound):
    exact = make_rule(workspace, keywords=["price"], keyword_match="exact", actions=[CLOSE])
    contains = make_rule(
        workspace, keywords=["rate card"], keyword_match="contains", actions=[CLOSE]
    )

    assert outcomes(process_inbound(inbound("Price?").pk)) == [(exact.pk, "succeeded")]
    assert process_inbound(inbound("price please").pk) == []
    assert outcomes(process_inbound(inbound("Send your RATE card pls").pk)) == [
        (contains.pk, "succeeded")
    ]
    assert process_inbound(inbound("rate cards").pk) == []
    assert process_inbound(inbound("").pk) == []


def test_rules_are_filtered_by_number_and_active_state(workspace, number, inbound):
    other_number = PhoneNumberFactory(workspace=workspace, waba=number.waba)
    this_number = make_rule(workspace, name="this number", phone_number=number)
    make_rule(workspace, name="other number", phone_number=other_number)
    make_rule(workspace, name="inactive", is_active=False)
    every_number = make_rule(workspace, name="every number")

    runs = process_inbound(inbound("price").pk)

    assert {run.rule_id for run in runs} == {this_number.pk, every_number.pk}


def test_rules_of_other_workspaces_never_run(other_workspace, inbound):
    AutomationRuleFactory(workspace=other_workspace)

    assert process_inbound(inbound("price").pk) == []
    assert not AutomationRun.objects.exists()


# --- Other triggers -----------------------------------------------------------------------------


def test_first_inbound_and_new_contact_triggers(workspace, inbound):
    first = make_rule(workspace, trigger="first_inbound", keywords=[], actions=[CLOSE])
    new = make_rule(workspace, trigger="new_contact", keywords=[], actions=[CLOSE])

    runs = process_inbound(inbound("hi").pk, is_first_inbound=True, contact_created=False)
    assert {run.rule_id for run in runs} == {first.pk}
    runs = process_inbound(inbound("hi").pk, is_first_inbound=True, contact_created=True)
    assert {run.rule_id for run in runs} == {first.pk, new.pk}
    assert process_inbound(inbound("hi").pk, is_first_inbound=False, contact_created=False) == []


def test_first_inbound_is_derived_from_stored_messages_when_not_given(workspace, inbound):
    first = make_rule(workspace, trigger="first_inbound", keywords=[], actions=[CLOSE])
    earlier, later = inbound("hello"), inbound("hello again")
    Message.objects.filter(pk=earlier.pk).update(created_at=timezone.now() - timedelta(minutes=5))

    assert outcomes(process_inbound(earlier.pk)) == [(first.pk, "succeeded")]
    assert process_inbound(later.pk) == []


def test_outside_business_hours_uses_the_message_time_in_the_workspace_zone(workspace, inbound):
    away = make_rule(
        workspace, trigger="outside_business_hours", keywords=[], actions=[text_action("Closed")]
    )
    BusinessHoursFactory(workspace=workspace)  # Mon-Sat 10:00-19:00

    monday_noon = datetime(2026, 9, 14, 12, 0, tzinfo=IST)
    assert process_inbound(inbound("hi", sent_at=monday_noon).pk) == []
    monday_night = datetime(2026, 9, 14, 21, 0, tzinfo=IST)
    assert outcomes(process_inbound(inbound("hi", sent_at=monday_night).pk)) == [
        (away.pk, "succeeded")
    ]
    sunday_noon = datetime(2026, 9, 13, 12, 0, tzinfo=IST)
    assert outcomes(process_inbound(inbound("hi", sent_at=sunday_noon).pk)) == [
        (away.pk, "succeeded")
    ]

    workspace.time_zone = "America/New_York"  # Monday 12:00 IST is 02:30 in New York
    workspace.save(update_fields=["time_zone"])
    assert outcomes(process_inbound(inbound("hi", sent_at=monday_noon).pk)) == [
        (away.pk, "succeeded")
    ]


def test_outside_business_hours_needs_enabled_hours(workspace, inbound):
    make_rule(workspace, trigger="outside_business_hours", keywords=[], actions=[CLOSE])

    assert process_inbound(inbound("hi").pk) == []  # hours never configured
    BusinessHoursFactory(workspace=workspace, enabled=False, schedule=[])
    assert process_inbound(inbound("hi").pk) == []


# --- Ordering -----------------------------------------------------------------------------------


def test_priority_order_and_stop_processing(workspace, inbound):
    low = make_rule(workspace, name="low", priority=20, actions=[CLOSE])
    high = make_rule(workspace, name="high", priority=10, actions=[CLOSE], stop_processing=True)

    assert outcomes(process_inbound(inbound("price").pk)) == [(high.pk, "succeeded")]

    AutomationRule.objects.filter(pk=high.pk).update(stop_processing=False)
    assert outcomes(process_inbound(inbound("price").pk)) == [
        (high.pk, "succeeded"),
        (low.pk, "succeeded"),
    ]


def test_equal_priorities_run_oldest_first(workspace, inbound):
    newer = make_rule(workspace, name="newer", actions=[CLOSE])
    older = make_rule(workspace, name="older", actions=[CLOSE])
    AutomationRule.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=1))

    assert [run.rule_id for run in process_inbound(inbound("price").pk)] == [older.pk, newer.pk]


def test_stop_processing_rule_without_a_match_does_not_stop_others(workspace, inbound):
    make_rule(workspace, keywords=["refund"], stop_processing=True, actions=[CLOSE])
    price = make_rule(workspace, priority=5, actions=[CLOSE])

    assert outcomes(process_inbound(inbound("price").pk)) == [(price.pk, "succeeded")]


# --- Guards -------------------------------------------------------------------------------------


def test_cooldown_skips_the_rule_and_still_stops_lower_rules(workspace, conversation, inbound):
    price = make_rule(workspace, cooldown_minutes=30, stop_processing=True)
    make_rule(workspace, name="fallback", priority=50, actions=[CLOSE])

    assert outcomes(process_inbound(inbound("price").pk)) == [(price.pk, "succeeded")]
    runs = process_inbound(inbound("price").pk)
    assert outcomes(runs) == [(price.pk, "skipped")]
    assert runs[0].detail.startswith("Cooldown")
    assert runs[0].action_results == []
    assert automation_messages(conversation).count() == 1
    price.refresh_from_db()
    assert price.run_count == 1

    # Another conversation has its own cooldown.
    elsewhere = ConversationFactory(
        workspace=workspace, phone_number=conversation.phone_number, window_open=True
    )
    message = MessageFactory(conversation=elsewhere, inbound=True, text="price")
    assert outcomes(process_inbound(message.pk)) == [(price.pk, "succeeded")]

    AutomationRun.objects.filter(rule=price, status="succeeded").update(
        created_at=timezone.now() - timedelta(minutes=31)
    )
    assert outcomes(process_inbound(inbound("price").pk)) == [(price.pk, "succeeded")]


def test_skipped_runs_do_not_extend_the_cooldown(workspace, inbound):
    price = make_rule(workspace, cooldown_minutes=30)
    process_inbound(inbound("price").pk)
    AutomationRun.objects.update(created_at=timezone.now() - timedelta(minutes=31))
    skipped = AutomationRun.objects.create(
        workspace=workspace,
        rule=price,
        conversation=AutomationRun.objects.get().conversation,
        message=inbound("price"),
        status=AutomationRun.Status.SKIPPED,
        detail="Cooldown",
    )

    assert skipped.status == "skipped"
    assert outcomes(process_inbound(inbound("price").pk)) == [(price.pk, "succeeded")]


def test_hourly_cap_on_automated_sends(workspace, conversation, inbound):
    MessageFactory.create_batch(
        MAX_AUTOMATED_SENDS_PER_HOUR - 1, conversation=conversation, source="automation"
    )
    rule = make_rule(workspace, actions=[text_action("one"), text_action("two")])

    runs = process_inbound(inbound("price").pk)
    assert outcomes(runs) == [(rule.pk, "skipped")]
    assert runs[0].detail.startswith("Hourly limit")
    assert automation_messages(conversation).count() == MAX_AUTOMATED_SENDS_PER_HOUR - 1

    AutomationRule.objects.filter(pk=rule.pk).update(actions=[text_action("one")])
    assert outcomes(process_inbound(inbound("price").pk)) == [(rule.pk, "succeeded")]
    assert automation_messages(conversation).count() == MAX_AUTOMATED_SENDS_PER_HOUR
    assert outcomes(process_inbound(inbound("price").pk)) == [(rule.pk, "skipped")]

    # Messages older than an hour no longer count.
    automation_messages(conversation).update(created_at=timezone.now() - timedelta(minutes=61))
    assert outcomes(process_inbound(inbound("price").pk)) == [(rule.pk, "succeeded")]


def test_rules_without_sends_are_not_capped(workspace, conversation, inbound):
    MessageFactory.create_batch(
        MAX_AUTOMATED_SENDS_PER_HOUR, conversation=conversation, source="automation"
    )
    rule = make_rule(workspace, actions=[CLOSE])

    assert outcomes(process_inbound(inbound("price").pk)) == [(rule.pk, "succeeded")]


def test_keyword_rules_are_skipped_when_the_plan_loses_the_feature(workspace, inbound, monkeypatch):
    monkeypatch.setattr(
        entitlements, "has_feature", lambda ws, feature: feature != entitlements.KEYWORD_AUTOMATIONS
    )
    rule = make_rule(workspace)
    welcome = make_rule(workspace, trigger="first_inbound", keywords=[], actions=[CLOSE])

    runs = process_inbound(inbound("price").pk, is_first_inbound=True)

    assert outcomes(runs) == [(rule.pk, "skipped"), (welcome.pk, "succeeded")]
    assert "plan" in runs[0].detail


# --- Never triggered ----------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["inbox", "campaign", "automation", "api"])
def test_outbound_messages_never_trigger(workspace, conversation, source):
    make_rule(workspace, trigger="first_inbound", keywords=[], actions=[CLOSE])
    make_rule(workspace)
    message = MessageFactory(conversation=conversation, text="price", source=source)

    assert process_inbound(message.pk, is_first_inbound=True) == []
    assert not AutomationRun.objects.exists()


def test_reactions_and_missing_messages_are_ignored(workspace, inbound):
    make_rule(workspace, trigger="first_inbound", keywords=[], actions=[CLOSE])

    reaction = inbound("👍", type=Message.Type.REACTION)
    assert process_inbound(reaction.pk, is_first_inbound=True) == []
    assert process_inbound(uuid.uuid4()) == []


# --- Actions ------------------------------------------------------------------------------------


def test_send_template_resolves_variable_sources(workspace, conversation, template, inbound):
    rule = make_rule(
        workspace,
        actions=[
            template_action(
                template,
                {"source": "contact_field", "value": "name", "fallback": "there"},
                {"source": "attribute", "value": "order_id", "fallback": ""},
            )
        ],
    )
    message = inbound("price")

    runs = process_inbound(message.pk)

    assert outcomes(runs) == [(rule.pk, "succeeded")]
    reply = automation_messages(conversation).get()
    assert reply.type == Message.Type.TEMPLATE
    assert reply.template == template
    assert reply.idempotency_key == f"automation:{rule.pk}:{message.wamid}:0"
    assert reply.template_components == [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Priya Sharma"},
                {"type": "text", "text": "1042"},
            ],
        }
    ]


def test_resolve_variable(contact):
    resolve = engine.resolve_variable

    assert resolve(contact, {"source": "contact_field", "value": "email"}) == "priya@example.com"
    assert resolve(contact, {"source": "attribute", "value": "city"}) == "Pune"
    assert resolve(contact, {"source": "attribute", "value": "tier", "fallback": "regular"}) == (
        "regular"
    )
    assert resolve(contact, {"source": "static", "value": "Diwali"}) == "Diwali"
    assert resolve(contact, {"source": "static", "value": "", "fallback": "Sale"}) == "Sale"
    assert resolve(contact, {"source": "contact_field", "value": "wa_id", "fallback": "-"}) == "-"
    contact.name = "  "
    assert resolve(contact, {"source": "contact_field", "value": "name", "fallback": "there"}) == (
        "there"
    )


def test_send_template_failures_are_logged(workspace, conversation, template, inbound):
    rule = make_rule(
        workspace,
        actions=[
            template_action(
                template,
                {"source": "attribute", "value": "missing", "fallback": ""},
                {"source": "static", "value": "x"},
            )
        ],
    )

    run = process_inbound(inbound("price").pk)[0]
    assert run.status == "failed"
    assert action_outcomes(run) == [("failed", "missing_variable")]

    static = [{"source": "static", "value": "a"}, {"source": "static", "value": "b"}]
    AutomationRule.objects.filter(pk=rule.pk).update(actions=[template_action(template, *static)])
    MessageTemplate.objects.filter(pk=template.pk).update(status=MessageTemplate.Status.PAUSED)
    run = process_inbound(inbound("price").pk)[0]
    assert action_outcomes(run) == [("failed", "template_not_approved")]

    template.delete()
    run = process_inbound(inbound("price").pk)[0]
    assert action_outcomes(run) == [("failed", "template_not_found")]
    assert not automation_messages(conversation).exists()


def test_tag_assign_and_close_actions(workspace, conversation, contact, inbound):
    vip, lead = TagFactory(workspace=workspace), TagFactory(workspace=workspace)
    agent = MembershipFactory(workspace=workspace, role=Role.AGENT).user
    make_rule(
        workspace,
        actions=[
            {"type": "add_tags", "config": {"tag_ids": [str(vip.pk), str(lead.pk)]}},
            {"type": "assign", "config": {"user_id": str(agent.pk)}},
            CLOSE,
        ],
    )

    run = process_inbound(inbound("price").pk)[0]

    assert run.status == "succeeded", run.detail
    assert run.detail == "Ran 3 action(s)."
    assert set(contact.tags.all()) == {vip, lead}
    conversation.refresh_from_db()
    assert conversation.assignee == agent
    assert conversation.status == Conversation.Status.CLOSED


def test_add_tags_skips_deleted_tags_and_fails_when_none_remain(workspace, contact, inbound):
    kept, deleted = TagFactory(workspace=workspace), TagFactory(workspace=workspace)
    rule = make_rule(
        workspace,
        actions=[{"type": "add_tags", "config": {"tag_ids": [str(kept.pk), str(deleted.pk)]}}],
    )
    deleted.delete()

    assert process_inbound(inbound("price").pk)[0].status == "succeeded"
    assert list(contact.tags.all()) == [kept]

    kept.delete()
    run = process_inbound(inbound("price").pk)[0]
    assert action_outcomes(run) == [("failed", "tags_not_found")]
    assert run.rule_id == rule.pk


def test_policy_failure_on_a_send_fails_the_run_and_halts_later_actions(
    workspace, conversation, contact, inbound
):
    tag = TagFactory(workspace=workspace)
    rule = make_rule(
        workspace,
        actions=[{"type": "add_tags", "config": {"tag_ids": [str(tag.pk)]}}, text_action(), CLOSE],
    )
    message = inbound("price")
    Conversation.objects.filter(pk=conversation.pk).update(
        service_window_expires_at=timezone.now() - timedelta(minutes=1)
    )

    runs = process_inbound(message.pk)

    assert outcomes(runs) == [(rule.pk, "failed")]
    run = runs[0]
    assert action_outcomes(run) == [
        ("succeeded", None),
        ("failed", "outside_service_window"),
        ("not_run", None),
    ]
    assert "outside_service_window" in run.detail
    assert "not run" in run.detail
    assert list(contact.tags.all()) == [tag]
    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.OPEN
    assert not automation_messages(conversation).exists()
    rule.refresh_from_db()
    assert rule.run_count == 1


def test_failed_non_send_action_does_not_halt_the_rest(workspace, conversation, inbound):
    outsider = UserFactory()
    make_rule(
        workspace,
        actions=[{"type": "assign", "config": {"user_id": str(outsider.pk)}}, text_action()],
    )

    run = process_inbound(inbound("price").pk)[0]

    assert run.status == "failed"
    assert action_outcomes(run) == [("failed", "assignee_not_member"), ("succeeded", None)]
    assert automation_messages(conversation).count() == 1


def test_unknown_stored_action_type_is_logged_as_failed(workspace, inbound):
    make_rule(workspace, actions=[{"type": "reboot", "config": {}}, CLOSE])

    run = process_inbound(inbound("price").pk)[0]

    assert action_outcomes(run) == [("failed", "unknown_action"), ("succeeded", None)]
