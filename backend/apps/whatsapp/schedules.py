from celery.schedules import crontab

BEAT_SCHEDULE = {
    "whatsapp.refresh_all_phone_numbers": {
        "task": "whatsapp.refresh_all_phone_numbers",
        "schedule": crontab(hour=3, minute=17),
    },
}
