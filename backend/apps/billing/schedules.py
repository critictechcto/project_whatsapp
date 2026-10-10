"""Celery beat entries for the billing app. Import-light: celery.schedules only.

Crontabs run in CELERY_TIMEZONE (Asia/Kolkata)."""

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "billing.expire_trials": {
        "task": "billing.expire_trials",
        "schedule": crontab(minute=7),
    },
    "billing.expire_prepaid": {
        "task": "billing.expire_prepaid",
        "schedule": crontab(minute=12),
    },
    "billing.send_renewal_reminders": {
        "task": "billing.send_renewal_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
}
