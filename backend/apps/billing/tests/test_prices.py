"""Plan prices from Razorpay plans: fetching and saving copies, the failure cache, GST back
calculation, the admin form, nullable API prices and the public plans endpoint."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.billing import invoices, prices
from apps.billing.admin import (
    NOT_FOUND_MESSAGE,
    UNREACHABLE_MESSAGE,
    PlanAdmin,
    PlanAdminForm,
)
from apps.billing.models import Plan, RazorpayPlan
from apps.billing.razorpay import RazorpayError
from apps.billing.views import PublicPlansView
from common.roles import Role

pytestmark = pytest.mark.django_db

PUBLIC_PLANS = "/api/v1/billing/public-plans/"
PLANS = "/api/v1/billing/plans/"
SUBSCRIPTION = "/api/v1/billing/subscription/"
UNREACHABLE = RazorpayError("Razorpay request failed (ConnectError).")


@pytest.fixture
def unpriced():
    """Forget the pre-saved copies so prices are fetched from the fake Razorpay."""
    RazorpayPlan.objects.all().delete()


def growth() -> Plan:
    return Plan.objects.get(slug="growth")


# --- Fetching and saving copies -------------------------------------------------------------


def test_a_miss_fetches_the_razorpay_plan_once_and_saves_a_copy(unpriced, fake_razorpay):
    plan = growth()

    first = prices.razorpay_plan(plan, "monthly")
    again = prices.razorpay_plan(plan, "monthly")

    assert first.pk == again.pk == "plan_test_growth_monthly"
    assert fake_razorpay.calls_to("fetch_plan") == [{"plan_id": "plan_test_growth_monthly"}]
    saved = RazorpayPlan.objects.get(pk="plan_test_growth_monthly")
    assert (saved.plan_id, saved.interval, saved.period, saved.period_interval) == (
        "growth",
        "monthly",
        "monthly",
        1,
    )
    assert (saved.amount_paise, saved.currency) == (294_882, "INR")
    assert saved.item_name == "Growth monthly"


def test_the_plan_field_wins_over_the_settings_fallback(unpriced, fake_razorpay):
    fake_razorpay.add_plan("plan_Growth2027", amount=354_000, name="Growth 2027")
    Plan.objects.filter(slug="growth").update(razorpay_plan_id_monthly="plan_Growth2027")

    assert growth().razorpay_plan_id("monthly") == "plan_Growth2027"
    assert growth().razorpay_plan_id("annual") == "plan_test_growth_annual"
    assert growth().price_paise("monthly") == 300_000


@pytest.mark.parametrize(
    ("period", "period_interval", "interval", "fits"),
    [
        ("monthly", 1, "monthly", True),
        ("yearly", 1, "annual", True),
        ("monthly", 12, "annual", True),
        ("yearly", 1, "monthly", False),
        ("monthly", 3, "monthly", False),
        ("weekly", 1, "monthly", False),
        ("monthly", 1, "annual", False),
    ],
)
def test_the_period_must_match_the_interval(
    unpriced, fake_razorpay, period, period_interval, interval, fits
):
    fake_razorpay.add_plan("plan_Check01", amount=100_000, period=period, interval=period_interval)
    field = f"razorpay_plan_id_{interval}"
    Plan.objects.filter(slug="growth").update(**{field: "plan_Check01"})

    if fits:
        assert prices.razorpay_plan(growth(), interval).amount_paise == 100_000
    else:
        with pytest.raises(prices.PlanPriceNotConfigured):
            prices.razorpay_plan(growth(), interval)
        assert growth().price_paise(interval) is None


def test_a_misfit_is_saved_so_it_is_not_fetched_again(unpriced, fake_razorpay):
    fake_razorpay.add_plan("plan_Weekly01", amount=100_000, period="weekly")
    Plan.objects.filter(slug="growth").update(razorpay_plan_id_monthly="plan_Weekly01")

    assert growth().price_paise("monthly") is None
    assert growth().price_paise("monthly") is None
    assert len(fake_razorpay.calls_to("fetch_plan")) == 1


def test_the_currency_must_be_inr(unpriced, fake_razorpay):
    fake_razorpay.add_plan("plan_Usd01", amount=3_000, currency="USD")
    Plan.objects.filter(slug="growth").update(razorpay_plan_id_monthly="plan_Usd01")

    with pytest.raises(prices.PlanPriceNotConfigured, match="USD"):
        prices.razorpay_plan(growth(), "monthly")


def test_no_id_is_not_configured(unpriced, settings, fake_razorpay):
    settings.RAZORPAY_PLAN_IDS = {}

    with pytest.raises(prices.PlanPriceNotConfigured):
        prices.razorpay_plan(growth(), "monthly")
    assert growth().price_paise("monthly") is None
    assert fake_razorpay.calls == []


def test_a_plan_razorpay_doesnt_know_is_not_found_and_remembered(unpriced, fake_razorpay):
    Plan.objects.filter(slug="growth").update(razorpay_plan_id_monthly="plan_Missing01")

    with pytest.raises(prices.RazorpayPlanNotFound):
        prices.razorpay_plan(growth(), "monthly")
    with pytest.raises(prices.RazorpayPlanNotFound):
        prices.razorpay_plan(growth(), "monthly")

    assert len(fake_razorpay.calls_to("fetch_plan")) == 1
    assert not RazorpayPlan.objects.exists()


def test_an_invalid_id_is_never_sent_to_razorpay(unpriced, fake_razorpay):
    Plan.objects.filter(slug="growth").update(razorpay_plan_id_monthly="plan_x/../orders")

    assert growth().price_paise("monthly") is None
    assert fake_razorpay.calls == []


def test_unreachable_razorpay_raises_and_is_remembered_for_a_minute(unpriced, fake_razorpay):
    fake_razorpay.fail_with = UNREACHABLE

    with pytest.raises(RazorpayError):
        prices.razorpay_plan(growth(), "monthly")
    fake_razorpay.fail_with = None
    with pytest.raises(RazorpayError):
        prices.razorpay_plan(growth(), "monthly")

    assert len(fake_razorpay.calls_to("fetch_plan")) == 1
    assert growth().price_paise("monthly") is None


@pytest.mark.parametrize("status_code", [429, 500, 502, 401])
def test_server_errors_count_as_unreachable(unpriced, fake_razorpay, status_code):
    fake_razorpay.fail_with = RazorpayError("nope", status_code=status_code)

    with pytest.raises(RazorpayError) as raised:
        prices.razorpay_plan(growth(), "monthly")

    assert not isinstance(raised.value, prices.PlanPriceNotConfigured)


def test_a_failure_is_remembered_for_60_seconds_only(unpriced, fake_razorpay, monkeypatch):
    timeouts = []
    real_set = prices.cache.set
    monkeypatch.setattr(
        prices.cache,
        "set",
        lambda key, value, timeout: timeouts.append(timeout) or real_set(key, value, timeout),
    )
    fake_razorpay.fail_with = UNREACHABLE
    assert growth().price_paise("monthly") is None
    fake_razorpay.fail_with = None

    prices.cache.clear()  # as if the 60 seconds had passed

    assert timeouts == [60]
    assert growth().price_paise("monthly") == 249_900


def test_a_saved_copy_needs_no_razorpay(fake_razorpay):
    fake_razorpay.fail_with = UNREACHABLE

    assert growth().price_paise("annual") == 2_499_000
    assert fake_razorpay.calls == []


def test_prefetch_prices_a_list_of_plans_in_one_query():
    plans = list(Plan.objects.all())

    with CaptureQueriesContext(connection) as queries:
        prices.prefetch(plans)
        result = [
            plan.price_paise(interval) for plan in plans for interval in ("monthly", "annual")
        ]

    assert len(queries) == 1
    assert None not in result


# --- GST back calculation -------------------------------------------------------------------


@pytest.mark.parametrize("base", [99_900, 249_900, 2_499_000, 5_999_000, 1, 7, 12_345])
@pytest.mark.parametrize(("buyer", "seller"), [("29", "29"), ("27", "29")])
def test_subtotal_for_total_inverts_compute_gst(base, buyer, seller):
    total = invoices.compute_gst(
        base, buyer_state_code=buyer, seller_state_code=seller, rate_percent=18
    ).total_paise

    found = invoices.subtotal_for_total(
        total, buyer_state_code=buyer, seller_state_code=seller, rate_percent=18
    )

    assert (
        invoices.compute_gst(
            found, buyer_state_code=buyer, seller_state_code=seller, rate_percent=18
        ).total_paise
        == total
    )


def test_without_gst_the_amount_is_the_price(settings):
    settings.BILLING_GST_ENABLED = False

    assert prices.base_price_paise(294_882) == 294_882
    assert (
        invoices.subtotal_for_total(
            1_001, buyer_state_code="", seller_state_code="29", rate_percent=0
        )
        == 1_001
    )


def test_with_gst_the_price_is_worked_back_from_the_amount(settings):
    settings.BILLING_GST_ENABLED = True
    settings.BILLING_GST_RATE_PERCENT = 18

    assert prices.base_price_paise(117_882) == 99_900
    assert prices.base_price_paise(294_882) == 249_900


def test_breakdown_for_total_always_adds_up():
    for total in range(10_000, 10_200):
        for buyer in ("29", "27"):
            breakdown = invoices.breakdown_for_total(
                total, buyer_state_code=buyer, seller_state_code="29", rate_percent=18
            )
            assert breakdown.total_paise == total
            assert breakdown.igst_paise == 0 or breakdown.cgst_paise == breakdown.sgst_paise == 0


# --- Admin ----------------------------------------------------------------------------------


def admin_form(**changes) -> PlanAdminForm:
    plan = growth()
    data = {
        "slug": plan.slug,
        "name": plan.name,
        "razorpay_plan_id_monthly": "",
        "razorpay_plan_id_annual": "",
        "limits": '{"members": 5}',
        "features": '["commerce"]',
        "is_active": True,
        "sort_order": 20,
        **changes,
    }
    return PlanAdminForm(data=data, instance=plan)


def test_admin_form_has_no_price_fields():
    assert set(PlanAdminForm().fields) == {
        "slug",
        "name",
        "razorpay_plan_id_monthly",
        "razorpay_plan_id_annual",
        "limits",
        "features",
        "is_active",
        "sort_order",
    }


def test_admin_form_accepts_matching_razorpay_plans_and_saves_their_copies(
    unpriced, fake_razorpay, rf, admin_user
):
    fake_razorpay.add_plan("plan_GrowthM", amount=294_882, name="Growth monthly 2027")
    fake_razorpay.add_plan("plan_GrowthY", amount=2_948_820, period="yearly")
    form = admin_form(
        razorpay_plan_id_monthly=" plan_GrowthM ", razorpay_plan_id_annual="plan_GrowthY"
    )

    assert form.is_valid(), form.errors
    plan = form.save(commit=False)
    request = rf.post("/admin/billing/plan/growth/change/")
    request.user = admin_user
    PlanAdmin(Plan, AdminSite()).save_model(request, plan, form, change=True)

    plan = growth()
    assert (plan.razorpay_plan_id_monthly, plan.razorpay_plan_id_annual) == (
        "plan_GrowthM",
        "plan_GrowthY",
    )
    assert set(RazorpayPlan.objects.filter(plan=plan).values_list("pk", "interval")) == {
        ("plan_GrowthM", "monthly"),
        ("plan_GrowthY", "annual"),
    }
    assert (plan.price_paise("monthly"), plan.price_paise("annual")) == (249_900, 2_499_000)


def test_admin_form_rejects_a_plan_razorpay_doesnt_know(fake_razorpay):
    form = admin_form(razorpay_plan_id_monthly="plan_LiveOnly01")

    assert not form.is_valid()
    assert form.errors["razorpay_plan_id_monthly"] == [NOT_FOUND_MESSAGE]


def test_admin_form_rejects_the_wrong_period_and_currency(fake_razorpay):
    fake_razorpay.add_plan("plan_Yearly01", amount=1_000_000, period="yearly")
    fake_razorpay.add_plan("plan_Usd01", amount=1_000, currency="USD")

    form = admin_form(
        razorpay_plan_id_monthly="plan_Yearly01", razorpay_plan_id_annual="plan_Usd01"
    )

    assert not form.is_valid()
    assert "bills every month" in form.errors["razorpay_plan_id_monthly"][0]
    assert "USD" in form.errors["razorpay_plan_id_annual"][0]


def test_admin_form_asks_to_try_again_when_razorpay_is_unreachable(fake_razorpay):
    fake_razorpay.fail_with = UNREACHABLE

    form = admin_form(razorpay_plan_id_monthly="plan_New01")

    assert not form.is_valid()
    assert form.errors["razorpay_plan_id_monthly"] == [UNREACHABLE_MESSAGE]


def test_admin_form_ignores_the_failure_cache(unpriced, fake_razorpay):
    fake_razorpay.fail_with = UNREACHABLE
    assert growth().price_paise("monthly") is None
    fake_razorpay.fail_with = None

    form = admin_form(razorpay_plan_id_monthly="plan_test_growth_monthly")

    assert form.is_valid(), form.errors
    assert growth().price_paise("monthly") == 249_900  # the cached failure was cleared


def test_admin_columns_show_amounts_names_and_the_settings_hint(fake_razorpay):
    admin = PlanAdmin(Plan, AdminSite())

    monthly = admin.monthly_razorpay_plan(growth())

    assert "₹2,948.82 charged (₹2,499 before GST)" in monthly
    assert "Growth monthly" in monthly
    assert "RAZORPAY_PLAN_IDS" in monthly


def test_admin_columns_show_unset_and_unreachable_plans(unpriced, settings, fake_razorpay):
    admin = PlanAdmin(Plan, AdminSite())
    fake_razorpay.fail_with = UNREACHABLE

    assert admin.annual_razorpay_plan(growth()) == "Razorpay unreachable"
    settings.RAZORPAY_PLAN_IDS = {}
    assert admin.annual_razorpay_plan(growth()) == "Not set: can't be bought"


def test_razorpay_plan_copies_are_read_only_in_the_admin(rf, admin_user):
    from apps.billing.admin import RazorpayPlanAdmin

    request = rf.get("/admin/")
    request.user = admin_user
    admin = RazorpayPlanAdmin(RazorpayPlan, AdminSite())

    assert not admin.has_add_permission(request)
    assert not admin.has_change_permission(request)
    assert not admin.has_delete_permission(request)


# --- API ------------------------------------------------------------------------------------


def test_public_plans_need_no_authentication_or_workspace():
    response = APIClient().get(PUBLIC_PLANS)

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["gst_rate_percent"] == 18
    assert [plan["id"] for plan in body["plans"]] == ["starter", "growth", "pro"]
    assert body["plans"][1]["monthly_price_paise"] == 249_900
    assert body["plans"][1]["annual_price_paise"] == 2_499_000
    assert body["plans"][1]["limits"] == {"whatsapp_numbers": 2, "members": 5, "contacts": 25000}
    assert response["Access-Control-Allow-Origin"] == "*"
    assert "Access-Control-Allow-Credentials" not in response
    assert response["Cache-Control"] == "public, max-age=300"


def test_public_plans_list_active_plans_only():
    Plan.objects.filter(slug="starter").update(is_active=False)

    body = APIClient().get(PUBLIC_PLANS).json()

    assert [plan["id"] for plan in body["plans"]] == ["growth", "pro"]


def test_public_plans_are_throttled_per_ip():
    view = PublicPlansView()

    assert view.throttle_scope == "public_plans"
    assert [throttle.__name__ for throttle in view.throttle_classes] == ["ScopedRateThrottle"]
    assert view.authentication_classes == []


def test_public_plans_show_null_prices_when_razorpay_is_unreachable(unpriced, fake_razorpay):
    fake_razorpay.fail_with = UNREACHABLE

    response = APIClient().get(PUBLIC_PLANS)

    assert response.status_code == 200
    plans = response.json()["plans"]
    assert all(plan["monthly_price_paise"] is None for plan in plans)
    assert all(plan["annual_price_paise"] is None for plan in plans)
    # Six ids, each fetched once; the next request is answered from the failure cache.
    APIClient().get(PUBLIC_PLANS)
    assert len(fake_razorpay.calls_to("fetch_plan")) == 6


def test_plan_list_and_subscription_have_null_prices_for_unbuyable_intervals(auth_client, settings):
    settings.RAZORPAY_PLAN_IDS = {"growth": {"monthly": "plan_test_growth_monthly"}}

    plans = {plan["id"]: plan for plan in auth_client(Role.VIEWER).get(PLANS).json()}
    subscription = auth_client(Role.VIEWER).get(SUBSCRIPTION)

    assert (plans["growth"]["monthly_price_paise"], plans["growth"]["annual_price_paise"]) == (
        249_900,
        None,
    )
    assert plans["pro"]["monthly_price_paise"] is None
    assert subscription.status_code == 200
    assert subscription.json()["plan"]["annual_price_paise"] is None
