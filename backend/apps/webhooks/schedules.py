"""Celery beat entries for the webhooks app. Import-light: celery.schedules only."""

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "webhooks.requeue_stuck_events": {
        "task": "webhooks.requeue_stuck_events",
        "schedule": crontab(minute="*/10"),
    },
    "webhooks.purge_old_events": {
        "task": "webhooks.purge_old_events",
        "schedule": crontab(hour=3, minute=17),
    },
}
