"""The order status machine matches the contract's transition table."""

import pytest

from apps.orders import transitions
from apps.orders.exceptions import InvalidOrderTransition
from apps.orders.schema_enums import ORDER_STAGES, ORDER_STATUSES

CHECKOUT = [
    "draft",
    "awaiting_confirmation",
    "awaiting_address",
    "awaiting_payment_method",
    "pending_payment",
]

EXPECTED = {
    **{status: ["cancelled"] for status in CHECKOUT},
    "confirmed": ["packed", "shipped", "cancelled"],
    "packed": ["shipped", "cancelled"],
    "shipped": ["delivered"],
    "needs_attention": ["confirmed", "cancelled"],
    "delivered": [],
    "cancelled": [],
    "expired": [],
}


def test_every_status_has_a_row():
    assert set(transitions.TRANSITIONS) == set(ORDER_STATUSES)
    assert set(EXPECTED) == set(ORDER_STATUSES)


@pytest.mark.parametrize("status", ORDER_STATUSES)
def test_manual_transitions_match_the_contract(status):
    assert transitions.allowed_transitions(status) == EXPECTED[status]


@pytest.mark.parametrize("status", ORDER_STATUSES)
def test_every_move_outside_the_table_is_rejected(status):
    for target in ORDER_STATUSES:
        allowed = target in EXPECTED[status]
        assert transitions.can_transition(status, target) is allowed
        if not allowed:
            with pytest.raises(InvalidOrderTransition) as caught:
                transitions.check_transition(status, target)
            assert caught.value.default_code == "invalid_order_transition"
            assert caught.value.detail == {
                "from_status": status,
                "to_status": target,
                "allowed": EXPECTED[status],
            }


def test_system_can_advance_expire_and_flag_checkouts():
    allowed = transitions.allowed_transitions("awaiting_address", system=True)
    assert allowed == [
        "awaiting_confirmation",
        "awaiting_payment_method",
        "pending_payment",
        "confirmed",
        "cancelled",
        "expired",
        "needs_attention",
    ]
    transitions.check_transition("pending_payment", "confirmed", system=True)
    with pytest.raises(InvalidOrderTransition):
        transitions.check_transition("pending_payment", "confirmed")


@pytest.mark.parametrize("status", ["confirmed", "shipped", "delivered", "cancelled", "expired"])
def test_system_gets_no_extra_moves_after_checkout(status):
    assert transitions.allowed_transitions(status, system=True) == EXPECTED[status]


def test_stages_partition_the_statuses():
    assert set(transitions.STAGE_STATUSES) == set(ORDER_STAGES)
    grouped = [status for statuses in transitions.STAGE_STATUSES.values() for status in statuses]
    assert sorted(grouped) == sorted(ORDER_STATUSES)
    assert transitions.stage_of("draft") == "checkout"
    assert transitions.stage_of("needs_attention") == "open"
    assert transitions.stage_of("expired") == "closed"
    with pytest.raises(ValueError):
        transitions.stage_of("lost")
