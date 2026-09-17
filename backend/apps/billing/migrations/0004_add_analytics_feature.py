"""Add the ``analytics`` feature to the existing Growth and Pro plans. Safe to re-run."""

from django.db import migrations

FEATURE = "analytics"
PLAN_SLUGS = ("growth", "pro")


def with_analytics(features) -> list:
    features = list(features or [])
    if FEATURE not in features:
        features.append(FEATURE)
    return features


def add_analytics(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.filter(slug__in=PLAN_SLUGS):
        features = with_analytics(plan.features)
        if features != plan.features:
            plan.features = features
            plan.save(update_fields=["features"])


def remove_analytics(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.filter(slug__in=PLAN_SLUGS):
        features = [feature for feature in plan.features or [] if feature != FEATURE]
        if features != plan.features:
            plan.features = features
            plan.save(update_fields=["features"])


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_add_commerce_feature")]

    operations = [migrations.RunPython(add_analytics, remove_analytics)]
