"""Celery beat entries for the campaigns app. Import-light: celery.schedules only."""

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "campaigns.start_due": {
        "task": "campaigns.start_due",
        "schedule": crontab(minute="*"),
    },
}
