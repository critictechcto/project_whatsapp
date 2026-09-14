"""Contact quota: single creates are checked, imports create new contacts only up to the limit."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.billing import entitlements
from apps.billing import services as billing_services
from apps.billing.models import Plan, Subscription
from apps.contacts import tasks
from apps.contacts.factories import ContactFactory
from apps.contacts.models import Contact, ContactImport

pytestmark = pytest.mark.django_db

CONTACTS = reverse("contacts:contact-list")
IMPORTS = reverse("contacts:import-list")


def limit_contacts(workspace, limit: int) -> None:
    """Give the workspace's plan a small contact limit (rolled back with the test)."""
    subscription = billing_services.get_subscription(workspace)
    plan = Plan.objects.get(pk=subscription.plan_id)
    Plan.objects.filter(pk=plan.pk).update(limits={**plan.limits, "contacts": limit})
    entitlements.clear_cache(workspace)


@pytest.fixture
def upload(auth_client, django_capture_on_commit_callbacks):
    def post(content: str):
        body = {"file": SimpleUploadedFile("contacts.csv", content.encode(), "text/csv")}
        with django_capture_on_commit_callbacks(execute=True):
            response = auth_client().post(IMPORTS, body, format="multipart")
        assert response.status_code == 201, response.content
        return ContactImport.objects.get(pk=response.json()["id"])

    return post


def test_create_is_refused_at_the_limit_but_updates_are_not(auth_client, workspace):
    limit_contacts(workspace, 1)
    existing = ContactFactory(workspace=workspace)
    client = auth_client()

    created = client.post(CONTACTS, {"phone_e164": "9876543210"})
    updated = client.patch(
        reverse("contacts:contact-detail", args=[existing.pk]), {"name": "Renamed"}
    )

    assert created.status_code == 409, created.content
    assert created.json()["error"]["code"] == "quota_exceeded"
    assert created.json()["error"]["details"] == {"metric": "contacts", "limit": 1, "used": 1}
    assert updated.status_code == 200, updated.content
    assert Contact.objects.filter(workspace=workspace).count() == 1


def test_create_within_the_limit(auth_client, workspace):
    limit_contacts(workspace, 1)

    response = auth_client().post(CONTACTS, {"phone_e164": "9876543210"})

    assert response.status_code == 201, response.content


def test_import_skips_new_contacts_over_the_limit(upload, workspace, monkeypatch):
    monkeypatch.setattr(tasks, "BATCH_SIZE", 2)
    limit_contacts(workspace, 3)
    ContactFactory(workspace=workspace, phone_e164="+919876543219", name="Kept")
    csv = (
        "phone,name\n"
        "9876543210,Asha\n"  # line 2: created
        "9876543219,Updated\n"  # line 3: existing, updated
        "9876543211,Ravi\n"  # line 4: created (fills the limit, next batch)
        "9876543212,Neha\n"  # line 5: over the limit
        "9876543213,Kiran\n"  # line 6: over the limit
        "9876543212,Neha again\n"  # line 7: same phone, still over the limit
    )

    job = upload(csv)

    assert job.status == ContactImport.Status.COMPLETED
    assert (job.created_count, job.updated_count, job.skipped_count) == (2, 1, 2)
    assert Contact.objects.filter(workspace=workspace).count() == 3
    assert Contact.objects.get(workspace=workspace, phone_e164="+919876543219").name == "Updated"
    assert not Contact.objects.filter(phone_e164__in=["+919876543212", "+919876543213"]).exists()
    quota_errors = [error for error in job.errors if error.get("reason") == "quota_exceeded"]
    assert [error["row"] for error in quota_errors] == [5, 6]
    assert all("contact limit" in error["error"] for error in quota_errors)


def test_import_on_an_expired_subscription_only_updates(upload, workspace):
    ContactFactory(workspace=workspace, phone_e164="+919876543219", name="Kept")
    subscription = billing_services.get_subscription(workspace)
    Subscription.objects.filter(pk=subscription.pk).update(status="expired")

    job = upload("phone,name\n9876543219,Updated\n9876543210,New\n")

    assert job.status == ContactImport.Status.COMPLETED
    assert (job.created_count, job.updated_count, job.skipped_count) == (0, 1, 1)
    assert job.errors == [
        {"row": 3, "error": tasks.QUOTA_EXCEEDED_MESSAGE, "reason": "quota_exceeded"}
    ]


def test_import_errors_expose_the_reason(auth_client, upload, workspace):
    limit_contacts(workspace, 0)
    job = upload("phone\n9876543210\n")

    response = auth_client().get(reverse("contacts:import-detail", args=[job.pk]))

    assert response.json()["errors"] == [
        {"row": 2, "error": tasks.QUOTA_EXCEEDED_MESSAGE, "reason": "quota_exceeded"}
    ]
