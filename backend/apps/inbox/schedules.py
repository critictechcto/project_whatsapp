"""Celery beat entries for the inbox app. Import-light: celery.schedules only."""

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "inbox.fail_stuck_messages": {
        "task": "inbox.fail_stuck_messages",
        "schedule": crontab(minute="*/5"),
    },
}
