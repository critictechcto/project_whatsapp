"""Celery beat entries for the offers app. Import-light: celery.schedules only."""

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "offers.expire_claims": {
        "task": "offers.expire_claims",
        "schedule": crontab(hour=1, minute=15),
    },
}
