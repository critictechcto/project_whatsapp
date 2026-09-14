from celery.schedules import crontab

BEAT_SCHEDULE = {
    "message_templates.sync_all": {
        "task": "message_templates.sync_all",
        "schedule": crontab(minute=17),  # hourly, off the top of the hour
    },
}
