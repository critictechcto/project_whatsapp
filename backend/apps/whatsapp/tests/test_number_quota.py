"""WhatsApp number quota at Embedded Signup: new numbers count, reconnecting doesn't."""

import pytest

from apps.billing import entitlements
from apps.billing import services as billing_services
from apps.billing.entitlements import QuotaExceeded
from apps.billing.models import Subscription
from apps.whatsapp import services
from apps.whatsapp.factories import PhoneNumberFactory
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount

from .conftest import PHONE_ID, SIGNUP_CODE, WABA_ID

pytestmark = pytest.mark.django_db


def use_starter(workspace) -> None:
    """Starter allows one WhatsApp number."""
    subscription = billing_services.get_subscription(workspace)
    Subscription.objects.filter(pk=subscription.pk).update(plan_id="starter")
    entitlements.clear_cache(workspace)


def signup(workspace, user):
    return services.complete_embedded_signup(
        workspace=workspace,
        user=user,
        code=SIGNUP_CODE,
        waba_id=WABA_ID,
        phone_number_id=PHONE_ID,
    )


def test_a_new_number_over_the_limit_is_refused_before_anything_is_stored(
    workspace, user, meta_signup
):
    use_starter(workspace)
    PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)

    with pytest.raises(QuotaExceeded) as caught:
        signup(workspace, user)

    assert caught.value.detail == {"metric": "whatsapp_numbers", "limit": 1, "used": 1}
    assert not WhatsAppBusinessAccount.objects.filter(waba_id=WABA_ID).exists()
    assert not PhoneNumber.objects.filter(phone_number_id=PHONE_ID).exists()


def test_reconnecting_a_connected_number_is_not_blocked(
    workspace, user, meta_signup, django_capture_on_commit_callbacks
):
    use_starter(workspace)
    with django_capture_on_commit_callbacks(execute=True):
        signup(workspace, user)  # the first number fits the limit

    with django_capture_on_commit_callbacks(execute=True):
        waba = signup(workspace, user)  # re-sync: the fake accepts the same code again

    assert waba.phone_numbers.count() == 1


def test_a_deregistered_number_counts_as_new(workspace, user, meta_signup):
    use_starter(workspace)
    signup(workspace, user)
    PhoneNumber.objects.filter(phone_number_id=PHONE_ID).update(
        registration_status=PhoneNumber.RegistrationStatus.DEREGISTERED
    )
    PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)

    with pytest.raises(QuotaExceeded):
        signup(workspace, user)


def test_expired_subscription_blocks_new_numbers(workspace, user, meta_signup):
    subscription = billing_services.get_subscription(workspace)
    Subscription.objects.filter(pk=subscription.pk).update(status="expired")

    with pytest.raises(QuotaExceeded):
        signup(workspace, user)
