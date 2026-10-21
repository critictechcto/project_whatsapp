from celery import shared_task
from django.conf import settings
from django.utils import timezone

from common.mail import send_or_retry

from . import services
from .invoices import INDIA_TZ
from .models import Subscription


@shared_task(name="billing.expire_trials")
def expire_trials() -> int:
    """Hourly: trials that ended without an activated Razorpay subscription become expired."""
    return services.expire_trials()


@shared_task(name="billing.expire_prepaid")
def expire_prepaid() -> int:
    """Hourly: prepaid plans past their paid period become expired (or cancelled)."""
    return services.expire_prepaid()


@shared_task(name="billing.send_renewal_reminders")
def send_renewal_reminders() -> int:
    """Daily at 09:00 IST: email owners 7 days and 1 day before a prepaid plan ends."""
    return services.send_renewal_reminders()


def plans_link(workspace_id) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/app/w/{workspace_id}/billing/plans"


@shared_task(bind=True, name="billing.send_renewal_reminder_email")
def send_renewal_reminder_email(self, subscription_id: str, email: str, reminder_key: str) -> bool:
    """One renewal reminder. Skipped when the plan was renewed, cancelled or ended meanwhile."""
    subscription = (
        Subscription.objects.select_related("plan", "workspace").filter(pk=subscription_id).first()
    )
    if (
        subscription is None
        or subscription.renewal_reminder_key != reminder_key
        or subscription.status != Subscription.Status.ACTIVE
        or subscription.cancel_at_period_end
        or subscription.current_period_end is None
    ):
        return False
    ends_at = timezone.localtime(subscription.current_period_end, INDIA_TZ)
    days = services.renewal_reminder_days(subscription.current_period_end, timezone.now())
    annual = subscription.interval == Subscription.Interval.ANNUAL
    send_or_retry(
        self,
        to=email,
        template="billing_renewal_reminder",
        context={
            "workspace": subscription.workspace.name,
            "plan": subscription.plan.name,
            "interval": "year" if annual else "month",
            "ends_on": f"{ends_at:%d %b %Y}",
            "ends_tomorrow": days is not None and days <= 1,
            "email": email,
            "link": plans_link(subscription.workspace_id),
        },
        idempotency_key=f"renewal:{subscription.pk}:{reminder_key}:{email.lower()}"[:256],
    )
    return True
