"""Cashfree prepaid plans: BillingOrder, Subscription.provider and renewal reminders, a phone on
the billing profile, and provider-neutral invoice payment ids."""

import uuid

import django.db.models.deletion
from django.db import migrations, models

PROVIDER_CHOICES = [("razorpay", "Razorpay"), ("cashfree", "Cashfree")]


def mark_razorpay_rows(apps, schema_editor):
    Subscription = apps.get_model("billing", "Subscription")
    Invoice = apps.get_model("billing", "Invoice")
    Subscription.objects.filter(razorpay_subscription_id__isnull=False, provider="").update(
        provider="razorpay"
    )
    Invoice.objects.filter(payment_id__isnull=False, payment_provider="").update(
        payment_provider="razorpay"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0004_add_analytics_feature"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="provider",
            field=models.CharField(blank=True, choices=PROVIDER_CHOICES, max_length=16),
        ),
        migrations.AddField(
            model_name="subscription",
            name="renewal_reminder_key",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="billingprofile",
            name="phone",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.RenameField(
            model_name="invoice", old_name="razorpay_payment_id", new_name="payment_id"
        ),
        migrations.AddField(
            model_name="invoice",
            name="payment_provider",
            field=models.CharField(blank=True, choices=PROVIDER_CHOICES, max_length=16),
        ),
        migrations.CreateModel(
            name="BillingOrder",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "provider",
                    models.CharField(choices=PROVIDER_CHOICES, default="cashfree", max_length=16),
                ),
                ("order_id", models.CharField(max_length=64, unique=True)),
                (
                    "interval",
                    models.CharField(
                        choices=[("monthly", "Monthly"), ("annual", "Annual")], max_length=16
                    ),
                ),
                (
                    "amount_paise",
                    models.PositiveIntegerField(help_text="GST-inclusive, as charged."),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("paid", "Paid"),
                            ("failed", "Failed"),
                            ("expired", "Expired"),
                        ],
                        default="created",
                        max_length=16,
                    ),
                ),
                ("payment_session_id", models.CharField(blank=True, max_length=512)),
                ("cf_payment_id", models.CharField(blank=True, max_length=64)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("period_start", models.DateTimeField(blank=True, null=True)),
                ("period_end", models.DateTimeField(blank=True, null=True)),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="billing_orders",
                        to="billing.plan",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_%(class)s_set",
                        to="tenants.workspace",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "get_latest_by": "created_at",
                "abstract": False,
            },
        ),
        migrations.RunPython(mark_razorpay_rows, migrations.RunPython.noop),
    ]
