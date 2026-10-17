"""apply_to_checkout, release, the OrderStatusChanged lifecycle and expiry."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.factories import ProductFactory
from apps.offers import services
from apps.offers.factories import OfferClaimFactory, OfferCodeFactory
from apps.offers.models import OfferClaim
from apps.orders.factories import OrderFactory, OrderItemFactory
from apps.orders.models import Order
from common import events

pytestmark = pytest.mark.django_db

CLAIMED, APPLIED, REDEEMED, EXPIRED = "claimed", "applied", "redeemed", "expired"


@pytest.fixture
def order(workspace, contact, number):
    return OrderFactory(
        workspace=workspace,
        contact=contact,
        phone_number=number,
        status=Order.Status.AWAITING_CONFIRMATION,
        payment_status=Order.PaymentStatus.UNPAID,
        payment_method="",
        subtotal_paise=100000,
        total_paise=100000,
    )


@pytest.fixture
def claim(offer, contact):
    return OfferClaimFactory(offer=offer, contact=contact)


def test_claim_is_applied_to_the_checkout(order, claim):
    applied = services.apply_to_checkout(order)

    assert applied == services.AppliedOffer(claim_id=claim.pk, code="DIWALI", discount_paise=10000)
    claim.refresh_from_db()
    assert claim.status == APPLIED
    assert claim.order == order
    assert claim.discount_paise == 10000


def test_reapplying_recomputes_for_the_same_order(order, claim):
    services.apply_to_checkout(order)
    order.subtotal_paise = 50000
    order.save()

    applied = services.apply_to_checkout(order)

    assert applied.claim_id == claim.pk
    assert applied.discount_paise == 5000


def test_no_claim_means_no_offer(order, offer):
    assert services.apply_to_checkout(order) is None


def test_other_contacts_claims_are_not_used(order, offer):
    OfferClaimFactory(offer=offer)
    assert services.apply_to_checkout(order) is None


def test_newest_claim_wins(order, contact, workspace, offer):
    OfferClaimFactory(offer=offer, contact=contact)
    newer = OfferClaimFactory(
        offer=OfferCodeFactory(workspace=workspace, code="HOLI", discount_value=20),
        contact=contact,
    )
    assert services.apply_to_checkout(order).claim_id == newer.pk


def test_minimum_order_is_checked(order, claim, offer):
    offer.min_order_paise = 150000
    offer.save()
    assert services.apply_to_checkout(order) is None
    claim.refresh_from_db()
    assert claim.status == CLAIMED


def test_applied_claim_that_no_longer_qualifies_is_released(order, claim, offer):
    services.apply_to_checkout(order)
    offer.min_order_paise = 150000
    offer.save()

    assert services.apply_to_checkout(order) is None
    claim.refresh_from_db()
    assert claim.status == CLAIMED
    assert claim.order is None


def test_applies_to_matches_the_order_kind(order, claim, offer):
    offer.applies_to = "services"
    offer.save()
    assert services.apply_to_checkout(order) is None

    offer.applies_to = "products"
    offer.save()
    assert services.apply_to_checkout(order) is not None


def test_booking_orders_take_service_offers(order, claim, offer):
    offer.applies_to = "services"
    offer.save()
    order.kind = "booking"  # Order.kind comes with the bookings branch; read via getattr
    assert services.apply_to_checkout(order) is not None


def test_ended_or_inactive_offers_do_not_apply(order, claim, offer):
    offer.ends_at = timezone.now() - timedelta(minutes=1)
    offer.save()
    assert services.apply_to_checkout(order) is None


def test_max_uses_is_enforced(order, claim, offer):
    offer.max_uses = 1
    offer.save()
    OfferClaimFactory(offer=offer, status=REDEEMED)
    assert services.apply_to_checkout(order) is None


def test_release_for_order(order, claim):
    services.apply_to_checkout(order)

    services.release_for_order(order)

    claim.refresh_from_db()
    assert (claim.status, claim.order, claim.discount_paise) == (CLAIMED, None, 0)


# --- OrderStatusChanged -------------------------------------------------------------------------


def status_event(order, new_status, payment_status="unpaid", total=100000):
    return events.OrderStatusChanged(
        workspace_id=order.workspace_id,
        order_id=order.pk,
        order_number=order.number,
        contact_id=order.contact_id,
        phone_number_id=order.phone_number_id,
        old_status="confirmed",
        new_status=new_status,
        payment_status=payment_status,
        payment_method="online",
        total_paise=total,
        actor="system",
        actor_user_id=None,
        occurred_at=timezone.now(),
    )


@pytest.mark.parametrize("new_status", ["cancelled", "expired"])
def test_cancelled_orders_release_the_claim(order, claim, new_status):
    services.apply_to_checkout(order)

    events.emit(events.order_status_changed, status_event(order, new_status))
    events.emit(events.order_status_changed, status_event(order, new_status))

    claim.refresh_from_db()
    assert claim.status == CLAIMED
    assert claim.order is None


@pytest.mark.parametrize("payment_status", ["paid", "cod_collected"])
def test_delivered_and_paid_orders_redeem_the_claim(order, claim, payment_status):
    services.apply_to_checkout(order)

    events.emit(
        events.order_status_changed, status_event(order, "delivered", payment_status, 90000)
    )

    claim.refresh_from_db()
    assert claim.status == REDEEMED
    assert claim.bill_paise == 90000
    assert claim.redeemed_at is not None


def test_delivered_but_unpaid_keeps_the_claim_applied(order, claim):
    services.apply_to_checkout(order)
    events.emit(events.order_status_changed, status_event(order, "delivered", "cod_pending"))
    claim.refresh_from_db()
    assert claim.status == APPLIED


def test_completed_bookings_redeem_the_claim(order, claim):
    services.apply_to_checkout(order)
    events.emit(events.order_status_changed, status_event(order, "completed", "cod_pending"))
    claim.refresh_from_db()
    assert claim.status == REDEEMED


def test_redeemed_claims_are_not_released(order, claim):
    services.apply_to_checkout(order)
    events.emit(events.order_status_changed, status_event(order, "delivered", "paid"))
    events.emit(events.order_status_changed, status_event(order, "cancelled"))
    claim.refresh_from_db()
    assert claim.status == REDEEMED


def test_events_for_unknown_orders_are_ignored(order, claim):
    order.pk = uuid.uuid4()
    events.emit(events.order_status_changed, status_event(order, "cancelled"))
    claim.refresh_from_db()
    assert claim.status == CLAIMED


# --- Expiry -------------------------------------------------------------------------------------


def test_expire_claims_of_ended_offers(workspace, contact):
    ended = OfferCodeFactory(workspace=workspace, ends_at=timezone.now() - timedelta(hours=1))
    live = OfferCodeFactory(workspace=workspace)
    stale = OfferClaimFactory(offer=ended, contact=contact)
    used = OfferClaimFactory(offer=ended, status=REDEEMED)
    current = OfferClaimFactory(offer=live, contact=contact)

    from apps.offers.tasks import expire_claims

    assert expire_claims.delay().get() == 1

    statuses = dict(OfferClaim.objects.values_list("pk", "status"))
    assert statuses == {stale.pk: EXPIRED, used.pk: REDEEMED, current.pk: CLAIMED}


# --- Chosen items -------------------------------------------------------------------------------


def _chosen_items_offer(offer, *products):
    offer.applies_to = "items"
    offer.save()
    offer.products.set(products)
    return offer


def test_chosen_items_discount_only_their_lines(order, claim, offer, workspace):
    facial = ProductFactory(workspace=workspace, name="Diwali Glow facial")
    other = ProductFactory(workspace=workspace, name="Haircut")
    OrderItemFactory(order=order, product=facial, unit_price_paise=30000, quantity=1)
    OrderItemFactory(order=order, product=other, unit_price_paise=70000, quantity=1)
    _chosen_items_offer(offer, facial)

    applied = services.apply_to_checkout(order)

    assert applied.discount_paise == 3000  # 10% of the facial's ₹300 only


def test_chosen_items_need_one_in_the_order(order, claim, offer, workspace):
    other = ProductFactory(workspace=workspace)
    OrderItemFactory(order=order, product=other, unit_price_paise=100000, quantity=1)
    _chosen_items_offer(offer, ProductFactory(workspace=workspace))

    assert services.apply_to_checkout(order) is None
    claim.refresh_from_db()
    assert claim.status == CLAIMED


def test_chosen_items_minimum_counts_only_their_lines(order, claim, offer, workspace):
    facial = ProductFactory(workspace=workspace)
    OrderItemFactory(order=order, product=facial, unit_price_paise=30000, quantity=1)
    OrderItemFactory(
        order=order, product=ProductFactory(workspace=workspace), unit_price_paise=70000
    )
    _chosen_items_offer(offer, facial)
    offer.min_order_paise = 50000
    offer.save()

    assert services.apply_to_checkout(order) is None
