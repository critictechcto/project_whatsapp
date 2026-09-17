"""Index messages by (workspace, created_at) for the analytics reports."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inbox", "0003_message_source_commerce"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="message",
            index=models.Index(fields=["workspace", "created_at"], name="inbox_msg_ws_created_idx"),
        ),
    ]
