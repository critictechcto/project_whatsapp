"""Celery beat entries for the payments app. Import-light: celery.schedules only."""

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "payments.poll_open_links": {
        "task": "payments.poll_open_links",
        "schedule": crontab(),  # every minute
    },
}
