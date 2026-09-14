import uuid

import pytest

from apps.whatsapp.factories import PhoneNumberFactory, WhatsAppBusinessAccountFactory
from apps.whatsapp.models import WhatsAppBusinessAccount
from common.events import (
    AccountUpdate,
    PhoneNumberQualityUpdate,
    account_updated,
    emit,
    phone_number_quality_updated,
)

pytestmark = pytest.mark.django_db

Status = WhatsAppBusinessAccount.Status


# --- Phone number quality ----------------------------------------------------------------------


@pytest.fixture
def phone(workspace):
    return PhoneNumberFactory(
        waba__workspace=workspace,
        display_phone_number="+91 98000 41207",
        messaging_limit_tier="TIER_1K",
        quality_rating="GREEN",
    )


def quality_event(phone, **overrides):
    fields = {
        "workspace_id": phone.workspace_id,
        "waba_id": phone.waba.waba_id,
        "display_phone_number": "919800041207",
        "event": "DOWNGRADE",
        "current_limit": "TIER_10K",
        **overrides,
    }
    return PhoneNumberQualityUpdate(**fields)


def test_quality_update_refreshes_from_meta(phone, fake_graph, django_capture_on_commit_callbacks):
    fake_graph.add_phone_number(
        phone.waba.waba_id,
        phone.phone_number_id,
        quality_rating="YELLOW",
        messaging_limit_tier="TIER_10K",
    )

    for _ in range(2):
        with django_capture_on_commit_callbacks(execute=True):
            assert emit(phone_number_quality_updated, quality_event(phone)) == []

    phone.refresh_from_db()
    assert phone.quality_rating == "YELLOW"
    assert phone.messaging_limit_tier == "TIER_10K"
    assert len(fake_graph.calls_to("get_phone_number")) == 2


def test_quality_update_sets_tier_even_if_refresh_fails(
    phone, fake_graph, django_capture_on_commit_callbacks
):
    # The fake has no such number, so the refresh fails with a non-retryable error.
    with django_capture_on_commit_callbacks(execute=True):
        assert emit(phone_number_quality_updated, quality_event(phone)) == []

    phone.refresh_from_db()
    assert phone.messaging_limit_tier == "TIER_10K"
    assert phone.last_error


@pytest.mark.parametrize(
    "overrides",
    [
        {"workspace_id": uuid.uuid4()},
        {"waba_id": "999"},
        {"display_phone_number": "919999999999"},
        {"display_phone_number": ""},
    ],
)
def test_quality_update_ignores_unknown_numbers(phone, fake_graph, overrides):
    assert emit(phone_number_quality_updated, quality_event(phone, **overrides)) == []

    phone.refresh_from_db()
    assert phone.messaging_limit_tier == "TIER_1K"
    assert fake_graph.calls == []


def test_quality_update_requires_matching_waba_workspace(phone, other_workspace, fake_graph):
    event = quality_event(phone, workspace_id=other_workspace.pk)

    assert emit(phone_number_quality_updated, event) == []
    assert fake_graph.calls == []


# --- Account updates -----------------------------------------------------------------------------


@pytest.fixture
def waba(workspace):
    return WhatsAppBusinessAccountFactory(workspace=workspace)


def account_event(waba, event, **payload):
    return AccountUpdate(
        workspace_id=waba.workspace_id, waba_id=waba.waba_id, event=event, payload=payload
    )


@pytest.mark.parametrize(
    ("event", "payload", "status"),
    [
        ("DISABLED_UPDATE", {"ban_info": {"waba_ban_state": "DISABLE"}}, Status.DISABLED),
        (
            "DISABLED_UPDATE",
            {"ban_info": {"waba_ban_state": "SCHEDULE_FOR_DISABLE"}},
            Status.RESTRICTED,
        ),
        ("DISABLED_UPDATE", {}, Status.DISABLED),
        ("ACCOUNT_VIOLATION", {"violation_info": {"violation_type": "SCAM"}}, Status.RESTRICTED),
        (
            "ACCOUNT_RESTRICTION",
            {"restriction_info": [{"restriction_type": "RESTRICTED_ADD_PHONE_NUMBER_ACTION"}]},
            Status.RESTRICTED,
        ),
        ("PARTNER_REMOVED", {}, Status.DISCONNECTED),
    ],
)
def test_account_update_maps_status(waba, event, payload, status):
    assert emit(account_updated, account_event(waba, event, **payload)) == []

    waba.refresh_from_db()
    assert waba.status == status
    assert event in waba.last_error


def test_account_violation_note_includes_type(waba):
    emit(
        account_updated,
        account_event(waba, "ACCOUNT_VIOLATION", violation_info={"violation_type": "SCAM"}),
    )

    waba.refresh_from_db()
    assert "SCAM" in waba.last_error


def test_partner_removed_clears_token_and_default(waba):
    phone = PhoneNumberFactory(waba=waba, is_default=True)

    emit(account_updated, account_event(waba, "PARTNER_REMOVED"))

    waba.refresh_from_db()
    phone.refresh_from_db()
    assert waba.access_token == ""
    assert "Reconnect required" in waba.last_error
    assert phone.is_default is False


def test_reinstate_restores_active(waba):
    emit(
        account_updated,
        account_event(waba, "DISABLED_UPDATE", ban_info={"waba_ban_state": "DISABLE"}),
    )
    emit(
        account_updated,
        account_event(waba, "DISABLED_UPDATE", value={"ban_info": {"waba_ban_state": "REINSTATE"}}),
    )

    waba.refresh_from_db()
    assert waba.status == Status.ACTIVE


def test_account_update_is_idempotent(waba):
    event = account_event(waba, "DISABLED_UPDATE", ban_info={"waba_ban_state": "DISABLE"})
    emit(account_updated, event)
    waba.refresh_from_db()
    first_update = waba.updated_at

    emit(account_updated, event)

    waba.refresh_from_db()
    assert waba.updated_at == first_update
    assert waba.status == Status.DISABLED


def test_verified_account_only_adds_note(waba):
    emit(account_updated, account_event(waba, "VERIFIED_ACCOUNT"))

    waba.refresh_from_db()
    assert waba.status == Status.ACTIVE
    assert "VERIFIED_ACCOUNT" in waba.last_error


def test_account_update_ignores_unknown_events_and_accounts(waba, other_workspace):
    emit(account_updated, account_event(waba, "SOMETHING_NEW"))
    emit(
        account_updated,
        AccountUpdate(
            workspace_id=other_workspace.pk, waba_id=waba.waba_id, event="PARTNER_REMOVED"
        ),
    )
    emit(
        account_updated,
        AccountUpdate(workspace_id=waba.workspace_id, waba_id="nope", event="PARTNER_REMOVED"),
    )

    waba.refresh_from_db()
    assert waba.status == Status.ACTIVE
    assert waba.last_error == ""
    assert waba.access_token


def test_disconnected_account_stays_disconnected(waba):
    WhatsAppBusinessAccount.objects.filter(pk=waba.pk).update(status=Status.DISCONNECTED)

    emit(
        account_updated,
        account_event(waba, "DISABLED_UPDATE", ban_info={"waba_ban_state": "REINSTATE"}),
    )

    waba.refresh_from_db()
    assert waba.status == Status.DISCONNECTED
