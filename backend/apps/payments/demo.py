"""Demo payments data for ``manage.py seed_demo``: a test-mode Razorpay account without secrets
(the seller still pastes a key secret and verifies). Idempotent."""

from .models import PaymentAccount

DEMO_KEY_ID = "rzp_test_UpChatzDemo01"


def seed(workspace) -> None:
    PaymentAccount.objects.get_or_create(
        workspace=workspace,
        defaults={
            "provider": PaymentAccount.Provider.RAZORPAY,
            "mode": PaymentAccount.Mode.TEST,
            "key_id": DEMO_KEY_ID,
            "status": PaymentAccount.Status.NOT_CONFIGURED,
        },
    )
