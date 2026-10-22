"""Celery beat entries for the orders app. Import-light: celery.schedules only."""

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "orders.expire_checkouts": {
        "task": "orders.expire_checkouts",
        "schedule": crontab(minute="*/5"),
    },
    "orders.send_payment_reminders": {
        "task": "orders.send_payment_reminders",
        "schedule": crontab(minute="*/5"),
    },
    "orders.send_booking_reminders": {
        "task": "orders.send_booking_reminders",
        "schedule": crontab(minute="*/10"),
    },
}
