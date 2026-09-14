"""Celery beat entries for the billing app. Import-light: celery.schedules only."""

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "billing.expire_trials": {
        "task": "billing.expire_trials",
        "schedule": crontab(minute=7),
    },
}
