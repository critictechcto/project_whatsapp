"""Celery beat entries for the orders app. Import-light: celery.schedules only."""

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "orders.expire_checkouts": {
        "task": "orders.expire_checkouts",
        "schedule": crontab(minute="*/5"),
    },
}
