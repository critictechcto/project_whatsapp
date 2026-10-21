"""Prepaid plans on any gateway: ``Subscription.prepaid`` (set for every Cashfree plan) and a
gateway-neutral ``BillingOrder.payment_id``. Razorpay orders are billing orders too, so the
order provider no longer defaults to Cashfree."""

from django.db import migrations, models

PROVIDER_CHOICES = [("razorpay", "Razorpay"), ("cashfree", "Cashfree")]


def mark_cashfree_prepaid(apps, schema_editor):
    Subscription = apps.get_model("billing", "Subscription")
    Subscription.objects.filter(provider="cashfree", prepaid=False).update(prepaid=True)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0005_cashfree_billing"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="prepaid",
            field=models.BooleanField(default=False),
        ),
        migrations.RenameField(
            model_name="billingorder", old_name="cf_payment_id", new_name="payment_id"
        ),
        migrations.AlterField(
            model_name="billingorder",
            name="provider",
            field=models.CharField(choices=PROVIDER_CHOICES, max_length=16),
        ),
        migrations.RunPython(mark_cashfree_prepaid, migrations.RunPython.noop),
    ]
