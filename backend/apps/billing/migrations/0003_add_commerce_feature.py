"""Add the ``commerce`` feature (the WhatsApp store) to every existing plan. Safe to re-run."""

from django.db import migrations

FEATURE = "commerce"


def with_commerce(features) -> list:
    features = list(features or [])
    if FEATURE not in features:
        features.append(FEATURE)
    return features


def add_commerce(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.all():
        features = with_commerce(plan.features)
        if features != plan.features:
            plan.features = features
            plan.save(update_fields=["features"])


def remove_commerce(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.all():
        features = [feature for feature in plan.features or [] if feature != FEATURE]
        if features != plan.features:
            plan.features = features
            plan.save(update_fields=["features"])


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_seed_plans")]

    operations = [migrations.RunPython(add_commerce, remove_commerce)]
