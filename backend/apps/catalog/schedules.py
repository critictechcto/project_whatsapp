BEAT_SCHEDULE = {
    # Returns at once when no batch is pending and no product is under review.
    "catalog.poll_sync_status": {
        "task": "catalog.poll_sync_status",
        "schedule": 120.0,
    },
}
