import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.contacts import tasks
from apps.contacts.factories import ContactFactory, TagFactory
from apps.contacts.models import ConsentEvent, Contact, ContactImport
from common.roles import Role
from common.testing import assert_tenant_isolated, result_ids

pytestmark = pytest.mark.django_db

IMPORTS = reverse("contacts:import-list")


def import_url(job):
    return reverse("contacts:import-detail", args=[job.pk])


@pytest.fixture
def upload(auth_client, django_capture_on_commit_callbacks):
    """POST a CSV as the workspace owner and run the import task on commit (eager Celery)."""

    def post(content, *, client=None, name="contacts.csv", **data):
        raw = content.encode() if isinstance(content, str) else content
        body = {"file": SimpleUploadedFile(name, raw, content_type="text/csv"), **data}
        with django_capture_on_commit_callbacks(execute=True):
            return (client or auth_client()).post(IMPORTS, body, format="multipart")

    return post


def finished(response) -> ContactImport:
    assert response.status_code == 201, response.content
    return ContactImport.objects.get(pk=response.json()["id"])


@pytest.mark.parametrize("header", ["phone", "Phone_Number", "MOBILE", " WhatsApp ", "number"])
def test_phone_column_aliases(upload, workspace, header):
    job = finished(upload(f"{header}\n9876543210\n"))

    assert job.status == ContactImport.Status.COMPLETED
    assert (job.total_rows, job.created_count) == (1, 1)
    assert Contact.objects.get(workspace=workspace).phone_e164 == "+919876543210"


def test_name_email_and_attributes(upload, workspace):
    csv = "﻿Name,Mobile,EMAIL,City,Plan,Empty\nAsha,+91 98765 43210,asha@example.in,Pune,gold,\n"

    job = finished(upload(csv))

    assert job.status == ContactImport.Status.COMPLETED
    contact = Contact.objects.get(workspace=workspace)
    assert (contact.name, contact.email, contact.wa_id) == (
        "Asha",
        "asha@example.in",
        "919876543210",
    )
    assert contact.attributes == {"city": "Pune", "plan": "gold"}
    assert contact.marketing_opt_in_status == Contact.OptInStatus.UNKNOWN


def test_duplicate_rows_update_same_contact(upload, workspace):
    csv = "phone,name,city\n9876543210,Asha,\n+919876543210,,Pune\n\n98765 43211,Ravi,Delhi\n"

    job = finished(upload(csv))

    assert (job.total_rows, job.created_count, job.updated_count) == (3, 2, 0)
    asha = Contact.objects.get(workspace=workspace, phone_e164="+919876543210")
    assert (asha.name, asha.attributes) == ("Asha", {"city": "Pune"})
    assert Contact.objects.filter(workspace=workspace).count() == 2


def test_duplicates_across_batches_and_existing_contacts(upload, workspace, monkeypatch):
    monkeypatch.setattr(tasks, "BATCH_SIZE", 2)
    ContactFactory(
        workspace=workspace, phone_e164="+919876543219", name="Kept", attributes={"a": "1"}
    )
    csv = "phone,name,b\n9876543210,,\n9876543211,,\n9876543210,Asha,\n9876543219,,2\n"

    job = finished(upload(csv))

    assert (job.total_rows, job.created_count, job.updated_count) == (4, 2, 1)
    existing = Contact.objects.get(workspace=workspace, phone_e164="+919876543219")
    assert (existing.name, existing.attributes) == ("Kept", {"a": "1", "b": "2"})
    assert Contact.objects.get(workspace=workspace, phone_e164="+919876543210").name == "Asha"


def test_invalid_rows_are_counted_and_capped(upload, workspace):
    rows = "\n".join(["123"] * 150 + ["9876543210", "9876543211,not-an-email"])

    job = finished(upload(f"phone,email\n{rows}\n"))

    assert job.status == ContactImport.Status.COMPLETED
    assert (job.total_rows, job.created_count, job.error_count) == (152, 1, 151)
    assert len(job.errors) == 100
    assert job.errors[0]["row"] == 2
    assert "123" in job.errors[0]["error"]


def test_stops_at_max_rows(upload, workspace, settings):
    settings.CONTACT_IMPORT_MAX_ROWS = 2

    job = finished(upload("phone\n9876543210\n9876543211\n9876543212\n"))

    assert (job.total_rows, job.created_count) == (2, 2)
    assert "limit" in job.errors[-1]["error"]


def test_missing_phone_column_fails(upload, workspace):
    job = finished(upload("name,email\nAsha,a@example.in\n"))

    assert job.status == ContactImport.Status.FAILED
    assert job.finished_at is not None
    assert "phone column" in job.errors[-1]["error"]
    assert not Contact.objects.exists()


def test_non_utf8_file_fails(upload):
    job = finished(upload("phone,name\n9876543210,Jos\xe9\n".encode("utf-16")))

    assert job.status == ContactImport.Status.FAILED


def test_file_size_limit(upload, settings):
    settings.CONTACT_IMPORT_MAX_BYTES = 10

    response = upload("phone\n9876543210\n")

    assert response.status_code == 400
    assert "file" in response.json()["error"]["details"]
    assert not ContactImport.objects.exists()


def test_only_csv_files_accepted(upload):
    response = upload("phone\n9876543210\n", name="contacts.xlsx")

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"mark_opted_in": "true", "opt_in_source": "Website form"}, "consent_attested"),
        ({"mark_opted_in": "true", "consent_attested": "true"}, "opt_in_source"),
        (
            {"mark_opted_in": "true", "consent_attested": "true", "opt_in_source": "  "},
            "opt_in_source",
        ),
    ],
)
def test_opt_in_import_requires_attestation_and_source(upload, data, field):
    response = upload("phone\n9876543210\n", **data)

    assert response.status_code == 400
    assert field in response.json()["error"]["details"]
    assert not ContactImport.objects.exists()


def test_attested_import_opts_contacts_in(upload, workspace, user):
    job = finished(
        upload(
            "phone\n9876543210\n9876543211\n",
            mark_opted_in="true",
            consent_attested="true",
            opt_in_source="Checkout form",
        )
    )

    contacts = Contact.objects.filter(workspace=workspace)
    assert {c.marketing_opt_in_status for c in contacts} == {Contact.OptInStatus.OPTED_IN}
    assert {c.opt_in_source for c in contacts} == {"import"}
    events = ConsentEvent.objects.filter(workspace=workspace)
    assert events.count() == 2
    event = events.first()
    assert (event.action, event.source, event.actor) == ("opt_in", "import", user)
    assert str(job.pk) in event.evidence
    assert "Checkout form" in event.evidence


def test_opted_out_contacts_are_not_opted_in(upload, workspace):
    opted_out = ContactFactory(
        workspace=workspace,
        phone_e164="+919876543210",
        marketing_opt_in_status=Contact.OptInStatus.OPTED_OUT,
    )

    job = finished(
        upload(
            "phone,name\n9876543210,Asha\n9876543211,Ravi\n",
            mark_opted_in="true",
            consent_attested="true",
            opt_in_source="Checkout form",
        )
    )

    opted_out.refresh_from_db()
    assert opted_out.marketing_opt_in_status == Contact.OptInStatus.OPTED_OUT
    assert opted_out.name == "Asha"
    assert job.skipped_count == 1
    assert job.errors == [
        {"row": 2, "error": "Contact has opted out of marketing; imported without opting in."}
    ]
    assert not ConsentEvent.objects.filter(contact=opted_out).exists()
    assert ConsentEvent.objects.filter(workspace=workspace).count() == 1


def test_import_without_opt_in_leaves_consent_unknown(upload, workspace):
    finished(upload("phone\n9876543210\n", consent_attested="true", opt_in_source="Form"))

    assert Contact.objects.get(workspace=workspace).marketing_opt_in_status == "unknown"
    assert not ConsentEvent.objects.exists()


def test_tags_applied(upload, workspace):
    vip, leads = TagFactory(workspace=workspace), TagFactory(workspace=workspace)
    existing = ContactFactory(workspace=workspace, phone_e164="+919876543211", tags=[vip])

    job = finished(upload("phone\n9876543210\n9876543211\n", tag_ids=[str(vip.pk), str(leads.pk)]))

    assert set(job.tags.all()) == {vip, leads}
    for contact in Contact.objects.filter(workspace=workspace):
        assert set(contact.tags.all()) == {vip, leads}
    assert existing.tags.count() == 2


def test_foreign_tag_rejected(upload, other_workspace):
    foreign = TagFactory(workspace=other_workspace)

    response = upload("phone\n9876543210\n", tag_ids=[str(foreign.pk)])

    assert response.status_code == 400
    assert "tag_ids" in response.json()["error"]["details"]


def test_rerunning_completed_import_is_noop(upload, workspace):
    job = finished(
        upload(
            "phone,name\n9876543210,Asha\n",
            mark_opted_in="true",
            consent_attested="true",
            opt_in_source="Form",
        )
    )
    Contact.objects.filter(workspace=workspace).update(name="Edited")
    finished_at = job.finished_at

    tasks.import_csv.delay(str(job.pk))

    job.refresh_from_db()
    assert (job.status, job.created_count, job.finished_at) == ("completed", 1, finished_at)
    assert Contact.objects.get(workspace=workspace).name == "Edited"
    assert ConsentEvent.objects.count() == 1


def test_response_hides_file_url(upload):
    response = upload("phone\n9876543210\n")

    body = response.json()
    assert "file" not in body
    assert body["file_name"].endswith(".csv")
    assert body["status"] == "queued"


def test_import_roles(upload, auth_client, workspace):
    response = upload("phone\n9876543210\n", client=auth_client(Role.AGENT))
    assert response.status_code == 403

    job = finished(upload("phone\n9876543210\n", client=auth_client(Role.ADMIN)))

    agent = auth_client(Role.AGENT)
    assert result_ids(agent.get(IMPORTS)) == {str(job.pk)}
    assert agent.get(import_url(job)).json()["created_count"] == 1
    assert auth_client(Role.VIEWER).get(IMPORTS).status_code == 403


def test_imports_are_tenant_isolated(upload, auth_client, other_workspace):
    job = finished(upload("phone\n9876543210\n", client=auth_client(workspace=other_workspace)))

    assert_tenant_isolated(
        auth_client(), object_id=job.pk, list_url=IMPORTS, detail_url=import_url(job)
    )
    assert not Contact.objects.exclude(workspace=other_workspace).exists()
