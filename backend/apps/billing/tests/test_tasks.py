"""Trial expiry, plan seeding, model enums and demo data."""

import importlib
from datetime import timedelta

import pytest
from celery.schedules import crontab
from django.utils import timezone

from apps.billing import demo, entitlements, services, tasks
from apps.billing.gst import is_valid_gstin
from apps.billing.models import BillingProfile, Invoice, Plan, Subscription
from apps.billing.plans import DEFAULT_PLANS, plan_fields
from apps.billing.schedules import BEAT_SCHEDULE
from apps.billing.schema_enums import BILLING_INTERVALS, INVOICE_STATUSES, SUBSCRIPTION_STATUSES
from apps.tenants.factories import WorkspaceFactory

pytestmark = pytest.mark.django_db


def subscription_with(**fields) -> Subscription:
    subscription = services.get_subscription(WorkspaceFactory())
    Subscription.objects.filter(pk=subscription.pk).update(**fields)
    return subscription


def test_expire_trials_expires_only_ended_unpaid_trials():
    now = timezone.now()
    ended = subscription_with(trial_ends_at=now - timedelta(minutes=1), cancel_at_period_end=True)
    running = subscription_with(trial_ends_at=now + timedelta(days=1))
    abandoned_checkout = subscription_with(
        status="pending",
        razorpay_subscription_id="sub_abandoned",
        trial_ends_at=now - timedelta(hours=2),
    )
    paid = subscription_with(
        status="active",
        activated_at=now - timedelta(days=20),
        trial_ends_at=now - timedelta(days=10),
        current_period_end=now + timedelta(days=10),
    )
    retrying = subscription_with(
        status="pending",
        activated_at=now - timedelta(days=40),
        trial_ends_at=now - timedelta(days=30),
        current_period_end=now + timedelta(days=1),
    )

    assert tasks.expire_trials.apply().get() == 2

    statuses = dict(Subscription.objects.values_list("pk", "status"))
    assert statuses == {
        ended.pk: "expired",
        running.pk: "trialing",
        abandoned_checkout.pk: "expired",
        paid.pk: "active",
        retrying.pk: "pending",
    }
    assert Subscription.objects.get(pk=ended.pk).cancel_at_period_end is False
    assert tasks.expire_trials.apply().get() == 0


def test_a_new_trial_expires_after_14_days(workspace, time_machine):
    subscription = services.get_subscription(workspace)
    assert entitlements.remaining_quota(workspace, entitlements.CONTACTS) == 25000

    time_machine.move_to(subscription.trial_ends_at + timedelta(minutes=1))
    assert services.expire_trials() == 1

    entitlements.clear_cache(workspace)
    assert entitlements.remaining_quota(workspace, entitlements.CONTACTS) == 0


def test_expire_trials_runs_hourly():
    entry = BEAT_SCHEDULE["billing.expire_trials"]

    assert entry["task"] == tasks.expire_trials.name == "billing.expire_trials"
    assert entry["schedule"] == crontab(minute=7)


def test_seeded_plans_match_the_pricing_page():
    plans = {plan.slug: plan for plan in Plan.objects.all()}

    assert [
        (slug, plans[slug].monthly_price_paise, plans[slug].annual_price_paise)
        for slug in ("starter", "growth", "pro")
    ] == [("starter", 99900, 999000), ("growth", 249900, 2499000), ("pro", 599900, 5999000)]
    assert plans["pro"].limits == {"whatsapp_numbers": 5, "members": 15, "contacts": 100000}


def test_the_data_migration_seeds_the_default_catalogue():
    migration = importlib.import_module("apps.billing.migrations.0002_seed_plans")

    assert {spec["slug"]: plan_fields(spec) for spec in DEFAULT_PLANS} == migration.PLANS


def test_model_choices_match_the_contract_enums():
    assert tuple(Subscription.Status.values) == SUBSCRIPTION_STATUSES
    assert tuple(Subscription.Interval.values) == BILLING_INTERVALS
    assert tuple(Invoice.Status.values) == INVOICE_STATUSES


def test_demo_seed_is_idempotent(workspace):
    demo.seed(workspace)
    demo.seed(workspace)

    subscription = Subscription.objects.get(workspace=workspace)
    assert (subscription.status, subscription.plan_id) == ("trialing", "growth")
    profile = BillingProfile.objects.get(workspace=workspace)
    assert profile.is_complete
    assert is_valid_gstin(profile.gstin)
    assert profile.gstin[:2] == profile.state_code == "27"
    seeded = Invoice.objects.filter(workspace=workspace)
    assert seeded.count() == 2
    assert {invoice.status for invoice in seeded} == {"paid"}
    assert all(invoice.igst_paise > 0 for invoice in seeded)
