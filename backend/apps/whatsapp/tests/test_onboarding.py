from datetime import UTC, datetime

import pytest
from django.db import connection

from apps.whatsapp import services
from apps.whatsapp.client import errors
from apps.whatsapp.factories import PhoneNumberFactory, WhatsAppBusinessAccountFactory
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount
from apps.whatsapp.schedules import BEAT_SCHEDULE
from apps.whatsapp.tasks import (
    finish_onboarding,
    refresh_all_phone_numbers,
    refresh_phone_number,
)
from common.crypto import decrypt
from common.exceptions import Conflict, UpstreamUnavailable

from .conftest import PHONE_ID, SIGNUP_CODE, WABA_ID

pytestmark = pytest.mark.django_db

Status = WhatsAppBusinessAccount.Status
Onboarding = WhatsAppBusinessAccount.OnboardingStatus
Registration = PhoneNumber.RegistrationStatus


def signup(workspace, user, **kwargs):
    params = {"code": SIGNUP_CODE, "waba_id": WABA_ID, "phone_number_id": PHONE_ID, **kwargs}
    return services.complete_embedded_signup(workspace=workspace, user=user, **params)


def raw_column(table, column, pk):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {column} FROM {table} WHERE id = %s", [pk])  # noqa: S608
        return cursor.fetchone()[0]


# --- Embedded Signup ---------------------------------------------------------------------------


def test_signup_happy_path(
    workspace, user, fake_graph, meta_signup, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        waba = signup(workspace, user, business_id="555")

    waba.refresh_from_db()
    assert waba.workspace == workspace
    assert waba.status == Status.ACTIVE
    assert waba.onboarding_status == Onboarding.COMPLETED
    assert waba.name == "Sharma Traders"
    assert waba.business_id == "555"
    assert waba.connected_by == user
    assert waba.access_token == meta_signup
    assert waba.token_expires_at is None
    assert waba.subscribed_at is not None
    assert WABA_ID in fake_graph.subscribed_waba_ids

    phone = waba.phone_numbers.get()
    assert phone.phone_number_id == PHONE_ID
    assert phone.workspace == workspace
    assert phone.phone_e164 == "+919800041207"
    assert phone.quality_rating == PhoneNumber.QualityRating.GREEN
    assert phone.messaging_limit_tier == "TIER_1K"
    assert phone.throughput_level == "STANDARD"
    assert phone.meta_status == "CONNECTED"
    assert phone.registration_status == Registration.REGISTERED
    assert phone.is_default is True
    assert phone.is_coexistence is False
    assert len(phone.pin) == 6 and phone.pin.isdigit()
    assert fake_graph.registered_pins[PHONE_ID] == phone.pin

    stored_pin = raw_column("whatsapp_phonenumber", "pin", phone.pk)
    assert stored_pin != phone.pin
    assert decrypt(stored_pin) == phone.pin
    assert decrypt(raw_column("whatsapp_whatsappbusinessaccount", "access_token", waba.pk)) == (
        meta_signup
    )


def test_signup_enqueues_onboarding_only_on_commit(workspace, user, fake_graph, meta_signup):
    waba = signup(workspace, user)

    assert waba.status == Status.PENDING
    assert waba.onboarding_status == Onboarding.CODE_EXCHANGED
    assert fake_graph.calls_to("subscribe_app") == []


def test_signup_stores_token_expiry(workspace, user, fake_graph, meta_signup):
    fake_graph._token_debug[meta_signup]["expires_at"] = 1_900_000_000

    waba = signup(workspace, user)

    assert waba.token_expires_at == datetime.fromtimestamp(1_900_000_000, tz=UTC)


def test_signup_rejects_waba_outside_granted_scope(workspace, user, fake_graph):
    fake_graph.add_phone_number(WABA_ID, PHONE_ID)
    fake_graph.add_signup(SIGNUP_CODE, waba_id=WABA_ID, target_ids=["999999"])

    with pytest.raises(services.SignupRejected) as caught:
        signup(workspace, user)

    assert caught.value.status_code == 400
    assert caught.value.get_codes() == "waba_not_granted"
    assert not WhatsAppBusinessAccount.objects.exists()
    assert fake_graph.calls_to("get_waba") == []


@pytest.mark.parametrize("override", [{"is_valid": False}, {"app_id": "someone-else"}])
def test_signup_rejects_invalid_or_foreign_token(
    workspace, user, fake_graph, meta_signup, override
):
    fake_graph._token_debug[meta_signup].update(override)

    with pytest.raises(services.SignupRejected) as caught:
        signup(workspace, user)

    assert caught.value.get_codes() == "waba_not_granted"


def test_signup_rejects_bad_code(workspace, user, fake_graph, meta_signup):
    with pytest.raises(services.SignupRejected) as caught:
        signup(workspace, user, code="wrong")

    assert caught.value.get_codes() == "signup_code_invalid"


def test_signup_upstream_outage_is_503(workspace, user, fake_graph, meta_signup):
    fake_graph.fail("exchange_code", errors.NetworkError("timeout"))

    with pytest.raises(UpstreamUnavailable):
        signup(workspace, user)


def test_signup_rejects_phone_from_another_waba(workspace, user, fake_graph, meta_signup):
    fake_graph.add_phone_number("777", "888")

    with pytest.raises(services.SignupRejected) as caught:
        signup(workspace, user, phone_number_id="888")

    assert caught.value.get_codes() == "phone_number_not_in_waba"


def test_signup_waba_in_other_workspace_conflicts(
    workspace, other_workspace, user, fake_graph, meta_signup
):
    foreign = WhatsAppBusinessAccountFactory(workspace=other_workspace, waba_id=WABA_ID)

    with pytest.raises(Conflict) as caught:
        signup(workspace, user)

    assert caught.value.get_codes() == "waba_already_connected"
    foreign.refresh_from_db()
    assert foreign.workspace == other_workspace
    assert foreign.access_token != meta_signup


def test_signup_phone_in_other_workspace_conflicts(
    workspace, other_workspace, user, fake_graph, meta_signup
):
    PhoneNumberFactory(waba__workspace=other_workspace, phone_number_id=PHONE_ID)

    with pytest.raises(Conflict) as caught:
        signup(workspace, user)

    assert caught.value.get_codes() == "phone_number_already_connected"


def test_reconnect_in_same_workspace_replaces_token(
    workspace, user, fake_graph, meta_signup, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        first = signup(workspace, user)
    services.disconnect_waba(first)
    new_token = fake_graph.add_signup("signup-code-2", waba_id=WABA_ID)

    with django_capture_on_commit_callbacks(execute=True):
        second = signup(workspace, user, code="signup-code-2")

    second.refresh_from_db()
    assert second.pk == first.pk
    assert WhatsAppBusinessAccount.objects.count() == 1
    assert second.access_token == new_token
    assert second.status == Status.ACTIVE
    assert second.onboarding_status == Onboarding.COMPLETED
    assert len(fake_graph.calls_to("subscribe_app")) == 2
    # Already registered: not registered again. Default restored after the disconnect cleared it.
    assert len(fake_graph.calls_to("register_phone")) == 1
    assert second.phone_numbers.get().is_default is True


def test_existing_default_number_is_kept(workspace, user, fake_graph, meta_signup):
    existing = PhoneNumberFactory(waba__workspace=workspace, is_default=True)

    waba = signup(workspace, user)

    assert waba.phone_numbers.get().is_default is False
    existing.refresh_from_db()
    assert existing.is_default is True


def test_signup_normalizes_phone_fields_tolerantly(workspace, user, fake_graph, meta_signup):
    fake_graph.phone_numbers[PHONE_ID].update(
        display_phone_number="12", quality_rating="PURPLE", throughput={"level": "HIGH"}
    )

    phone = signup(workspace, user).phone_numbers.get()

    assert phone.phone_e164 == ""
    assert phone.quality_rating == PhoneNumber.QualityRating.UNKNOWN
    assert phone.throughput_level == "HIGH"


def test_coexistence_number_is_not_registered(
    workspace, user, fake_graph, meta_signup, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        waba = signup(workspace, user, coexistence=True)

    waba.refresh_from_db()
    phone = waba.phone_numbers.get()
    assert phone.is_coexistence is True
    assert phone.pin == ""
    assert phone.registration_status == Registration.PENDING
    assert fake_graph.calls_to("register_phone") == []
    assert waba.status == Status.ACTIVE
    assert waba.onboarding_status == Onboarding.COMPLETED


# --- finish_onboarding -------------------------------------------------------------------------


@pytest.fixture
def pending_waba(workspace, user, fake_graph, meta_signup):
    return signup(workspace, user)


@pytest.fixture
def eager_retries():
    """With task_eager_propagates, Celery re-raises Retry instead of re-running the task eagerly.
    Turning propagation off lets ``self.retry`` run the retries inline, as a worker would."""
    # The app reads Django settings with the CELERY_ namespace, so override the prefixed key.
    conf = finish_onboarding._get_app().conf
    previous = conf.task_eager_propagates
    conf.update(CELERY_TASK_EAGER_PROPAGATES=False)
    try:
        yield
    finally:
        conf.update(CELERY_TASK_EAGER_PROPAGATES=previous)


@pytest.mark.usefixtures("eager_retries")
def test_retryable_error_then_success(pending_waba, fake_graph):
    fake_graph.fail("subscribe_app", errors.TransientError("Temporary", code=1))
    fake_graph.fail("register_phone", errors.RateLimitedError("Slow down", code=130429))

    finish_onboarding.delay(str(pending_waba.pk))

    pending_waba.refresh_from_db()
    assert pending_waba.status == Status.ACTIVE
    assert pending_waba.onboarding_status == Onboarding.COMPLETED
    assert len(fake_graph.calls_to("subscribe_app")) == 2
    assert len(fake_graph.calls_to("register_phone")) == 2
    # The PIN is reused on retry so Meta's two-step PIN stays consistent.
    pins = {call.kwargs["pin"] for call in fake_graph.calls_to("register_phone")}
    assert len(pins) == 1


@pytest.mark.usefixtures("eager_retries")
def test_retries_exhausted_marks_failed(pending_waba, fake_graph):
    fake_graph.fail("subscribe_app", errors.NetworkError("timeout"), times=10)

    finish_onboarding.delay(str(pending_waba.pk))

    pending_waba.refresh_from_db()
    assert len(fake_graph.calls_to("subscribe_app")) == 6
    assert pending_waba.onboarding_status == Onboarding.FAILED
    assert pending_waba.last_error == "timeout"


def test_non_retryable_error_marks_failed(pending_waba, fake_graph, meta_signup):
    fake_graph.fail(
        "register_phone", errors.PhoneRegistrationError("Two-step PIN mismatch", code=133005)
    )

    finish_onboarding.delay(str(pending_waba.pk))

    pending_waba.refresh_from_db()
    assert len(fake_graph.calls_to("register_phone")) == 1
    assert pending_waba.status == Status.PENDING
    assert pending_waba.onboarding_status == Onboarding.FAILED
    assert pending_waba.last_error == "Two-step PIN mismatch"
    assert meta_signup not in pending_waba.last_error
    assert pending_waba.subscribed_at is not None
    phone = pending_waba.phone_numbers.get()
    assert phone.registration_status == Registration.FAILED
    assert phone.last_error == "Two-step PIN mismatch"


def test_finish_onboarding_is_idempotent(pending_waba, fake_graph):
    finish_onboarding.delay(str(pending_waba.pk))
    finish_onboarding.delay(str(pending_waba.pk))

    assert len(fake_graph.calls_to("subscribe_app")) == 1
    assert len(fake_graph.calls_to("register_phone")) == 1
    assert len(fake_graph.calls_to("get_phone_number")) == 2


def test_finish_onboarding_ignores_missing_or_disconnected(pending_waba, fake_graph):
    finish_onboarding.delay("00000000-0000-0000-0000-000000000000")
    WhatsAppBusinessAccount.objects.filter(pk=pending_waba.pk).update(status=Status.DISCONNECTED)
    finish_onboarding.delay(str(pending_waba.pk))

    assert fake_graph.calls_to("subscribe_app") == []


# --- Disconnect ----------------------------------------------------------------------------------


def test_disconnect_unsubscribes_and_clears_token(workspace, fake_graph):
    waba = WhatsAppBusinessAccountFactory(workspace=workspace)
    phone = PhoneNumberFactory(waba=waba, is_default=True)
    token = waba.access_token

    services.disconnect_waba(waba)

    waba.refresh_from_db()
    assert waba.status == Status.DISCONNECTED
    assert waba.access_token == ""
    assert fake_graph.calls_to("unsubscribe_app")[0].access_token == token
    phone.refresh_from_db()
    assert phone.is_default is False


def test_disconnect_tolerates_revoked_access(workspace, fake_graph):
    waba = WhatsAppBusinessAccountFactory(workspace=workspace)
    fake_graph.fail("unsubscribe_app", errors.TokenInvalidError("Session expired", code=190))

    services.disconnect_waba(waba)

    waba.refresh_from_db()
    assert waba.status == Status.DISCONNECTED


def test_disconnect_upstream_outage_keeps_account(workspace, fake_graph):
    waba = WhatsAppBusinessAccountFactory(workspace=workspace)
    fake_graph.fail("unsubscribe_app", errors.NetworkError("timeout"))

    with pytest.raises(UpstreamUnavailable):
        services.disconnect_waba(waba)

    waba.refresh_from_db()
    assert waba.status == Status.ACTIVE


# --- Refresh tasks -------------------------------------------------------------------------------


def test_refresh_phone_number_updates_fields(workspace, fake_graph):
    phone = PhoneNumberFactory(waba__workspace=workspace, quality_rating="GREEN")
    fake_graph.add_phone_number(
        phone.waba.waba_id,
        phone.phone_number_id,
        quality_rating="YELLOW",
        messaging_limit_tier="TIER_10K",
        verified_name="New Name",
        name_status="APPROVED",
        status="FLAGGED",
        throughput={"level": "HIGH"},
    )

    refresh_phone_number.delay(str(phone.pk))

    phone.refresh_from_db()
    assert phone.quality_rating == "YELLOW"
    assert phone.messaging_limit_tier == "TIER_10K"
    assert phone.verified_name == "New Name"
    assert phone.meta_status == "FLAGGED"
    assert phone.throughput_level == "HIGH"
    assert phone.last_synced_at is not None


def test_refresh_phone_number_token_invalid_requires_reconnect(workspace, fake_graph):
    phone = PhoneNumberFactory(waba__workspace=workspace)
    fake_graph.fail("get_phone_number", errors.TokenInvalidError("Session expired", code=190))

    refresh_phone_number.delay(str(phone.pk))

    phone.waba.refresh_from_db()
    assert phone.waba.status == Status.DISCONNECTED
    assert phone.waba.last_error == "Reconnect required"


def test_refresh_all_fans_out_over_active_accounts(workspace, fake_graph):
    active = PhoneNumberFactory(waba__workspace=workspace)
    restricted = PhoneNumberFactory(waba__workspace=workspace, waba__status=Status.RESTRICTED)
    PhoneNumberFactory(waba__workspace=workspace, waba__status=Status.DISCONNECTED)
    PhoneNumberFactory(waba__workspace=workspace, waba__status=Status.PENDING)
    for phone in (active, restricted):
        fake_graph.add_phone_number(phone.waba.waba_id, phone.phone_number_id)

    assert refresh_all_phone_numbers.delay().get() == 2

    refreshed = {call.kwargs["phone_number_id"] for call in fake_graph.calls_to("get_phone_number")}
    assert refreshed == {active.phone_number_id, restricted.phone_number_id}


def test_beat_schedule_refreshes_daily():
    entry = BEAT_SCHEDULE["whatsapp.refresh_all_phone_numbers"]
    assert entry["task"] == "whatsapp.refresh_all_phone_numbers"
    assert all(name.startswith("whatsapp.") for name in BEAT_SCHEDULE)
