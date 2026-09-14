from celery import shared_task

from . import services


@shared_task(name="billing.expire_trials")
def expire_trials() -> int:
    """Hourly: trials that ended without an activated Razorpay subscription become expired."""
    return services.expire_trials()
