"""Journey: a seller writes a marketing template, Meta approves it, contacts come in from a CSV
with recorded opt-in, and a scheduled campaign goes out, reports delivery and counts replies."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.campaigns.tasks import start_due
from apps.message_templates.factories import standard_components

from .conftest import status_update
from .test_journey_support import Customer, error, now_ts, ok, results, template_status_webhook

pytest_plugins = ["tests.test_journey_support"]
pytestmark = pytest.mark.django_db

UNDELIVERABLE = 131026
OPTED_IN_CSV = (
    "name,phone,city\n"
    "Priya Sharma,98765 43210,Delhi\n"
    "Arjun Mehta,+91 98123 45601,Pune\n"
    "Kavya Iyer,9812345602,Chennai\n"
    "Dev Patel,9812345603,Surat\n"
)
NO_CONSENT_CSV = "name,phone\nNeha Gupta,9812345604\n"


def upload_csv(seller_api, content: str, **fields):
    body = {"file": SimpleUploadedFile("contacts.csv", content.encode(), "text/csv"), **fields}
    job = ok(seller_api.post("/api/v1/contacts/imports/", body, format="multipart"), 201)
    return ok(seller_api.get(f"/api/v1/contacts/imports/{job['id']}/"))


def test_scheduled_marketing_campaign_from_template_to_replies(
    seller_api, seller_number_id, fake_graph, deliver_meta, time_machine
):
    [waba] = results(seller_api.get("/api/v1/whatsapp/accounts/"))

    # 1. Template: draft → submitted → approved by Meta's webhook.
    draft = ok(
        seller_api.post(
            "/api/v1/templates/",
            {
                "waba": waba["id"],
                "name": "diwali_offer",
                "language": "en",
                "category": "MARKETING",
                "components": standard_components(
                    "Hi {{1}}, Diwali sweets are here! Use code {{2}} for 10% off."
                ),
            },
        ),
        201,
    )
    assert draft["status"] == "DRAFT"
    submitted = ok(seller_api.post(f"/api/v1/templates/{draft['id']}/submit/"))
    assert submitted["status"] == "PENDING"
    assert submitted["meta_template_id"]
    template_url = f"/api/v1/templates/{draft['id']}/"

    # 2. Contacts: a tag, a CSV with attested opt-in, and one contact without consent.
    tag = ok(seller_api.post("/api/v1/contacts/tags/", {"name": "Diwali 2026"}), 201)
    job = upload_csv(
        seller_api,
        OPTED_IN_CSV,
        mark_opted_in="true",
        consent_attested="true",
        opt_in_source="Festive order form at the shop counter",
        tag_ids=[tag["id"]],
    )
    assert (job["status"], job["created_count"], job["error_count"]) == ("completed", 4, 0)
    job = upload_csv(seller_api, NO_CONSENT_CSV, tag_ids=[tag["id"]])
    assert (job["status"], job["created_count"]) == ("completed", 1)
    contacts = {
        c["name"]: c for c in results(seller_api.get("/api/v1/contacts/", {"page_size": 50}))
    }
    assert contacts["Priya Sharma"]["marketing_opt_in_status"] == "opted_in"
    assert contacts["Priya Sharma"]["opt_in_source"]
    assert contacts["Neha Gupta"]["marketing_opt_in_status"] != "opted_in"

    # 3. Campaign draft with audience and variables.
    campaign = ok(
        seller_api.post(
            "/api/v1/campaigns/",
            {
                "name": "Diwali offer",
                "template_id": draft["id"],
                "phone_number_id": seller_number_id,
                "audience": {"tag_ids": [tag["id"]], "match": "any", "contact_ids": []},
                "variable_mapping": {
                    "body": [
                        {"source": "contact_field", "value": "name", "fallback": "there"},
                        {"source": "static", "value": "DIWALI10", "fallback": ""},
                    ],
                    "header": None,
                    "buttons": {},
                },
            },
        ),
        201,
    )
    assert campaign["status"] == "draft"
    url = f"/api/v1/campaigns/{campaign['id']}/"
    preview = ok(seller_api.post(f"{url}audience-preview/"))
    assert (preview["total"], preview["eligible"]) == (5, 4)
    assert preview["skipped"]["not_opted_in"] == 1

    # Launch is refused while Meta is still reviewing the template, and without attestation.
    error(
        seller_api.post(f"{url}launch/", {"consent_attested": True}), 409, "template_not_approved"
    )
    deliver_meta(template_status_webhook(submitted["meta_template_id"], "diwali_offer", "APPROVED"))
    assert ok(seller_api.get(template_url))["status"] == "APPROVED"
    assert seller_api.post(f"{url}launch/", {"consent_attested": False}).status_code == 400

    # 4. Schedule it for later today.
    send_at = timezone.now().replace(microsecond=0) + timedelta(minutes=10)
    launched = ok(
        seller_api.post(
            f"{url}launch/", {"consent_attested": True, "scheduled_at": send_at.isoformat()}
        )
    )
    assert launched["status"] == "scheduled"
    assert launched["consent_attested"] is True
    assert parse_datetime(launched["scheduled_at"]) == send_at
    assert launched["estimated_cost"]["currency"] == "INR"
    assert fake_graph.sent_messages == []

    # Dev texts STOP before the send time: consent is re-checked at dispatch.
    dev = Customer(deliver_meta, wa_id="919812345603", name="Dev Patel")
    dev.says("STOP")
    [dev_contact] = results(seller_api.get("/api/v1/contacts/", {"search": "Dev"}))
    assert dev_contact["marketing_opt_in_status"] == "opted_out"

    time_machine.move_to(send_at + timedelta(seconds=30))
    with seller_api.run_on_commit():
        start_due.delay()

    sent = {m["to"]: m for m in fake_graph.sent_messages}
    assert set(sent) == {"919876543210", "919812345601", "919812345602"}
    priya_send = sent["919876543210"]
    assert priya_send["type"] == "template"
    assert priya_send["template"]["name"] == "diwali_offer"
    assert [p["text"] for p in priya_send["template"]["components"][0]["parameters"]] == [
        "Priya Sharma",
        "DIWALI10",
    ]

    recipients = {
        r["contact"]["name"]: r
        for r in results(seller_api.get(f"{url}recipients/", {"page_size": 50}))
    }
    assert recipients["Neha Gupta"]["status"] == "skipped"
    assert recipients["Dev Patel"]["status"] == "skipped"
    assert recipients["Priya Sharma"]["status"] == "sent"

    # 5. Delivery statuses from Meta.
    ts = now_ts()
    wamid = {to: message["wamid"] for to, message in sent.items()}
    for status, offset in (("sent", 1), ("delivered", 2), ("read", 3)):
        deliver_meta(
            status_update(wamid["919876543210"], status, ts + offset, wa_id="919876543210")
        )
    for status, offset in (("sent", 1), ("delivered", 2)):
        deliver_meta(
            status_update(wamid["919812345601"], status, ts + offset, wa_id="919812345601")
        )
    deliver_meta(
        status_update(
            wamid["919812345602"], "failed", ts + 2, wa_id="919812345602", error_code=UNDELIVERABLE
        )
    )

    body = ok(seller_api.get(url))
    assert body["status"] == "completed"
    assert body["stats"] == {
        "total": 5,
        "skipped": 2,
        "queued": 0,
        "sent": 2,
        "delivered": 2,
        "read": 1,
        "failed": 1,
        "replied": 0,
    }
    recipients = {
        r["contact"]["name"]: r
        for r in results(seller_api.get(f"{url}recipients/", {"page_size": 50}))
    }
    assert {name: r["status"] for name, r in recipients.items()} == {
        "Priya Sharma": "read",
        "Arjun Mehta": "delivered",
        "Kavya Iyer": "failed",
        "Dev Patel": "skipped",
        "Neha Gupta": "skipped",
    }
    assert recipients["Kavya Iyer"]["error_code"] == str(UNDELIVERABLE)
    assert recipients["Priya Sharma"]["message_id"]

    # 6. Priya replies (twice, with a redelivery): replied counts her once.
    priya = Customer(deliver_meta)
    reply = priya.says("Do you deliver to Noida?")
    deliver_meta(reply)
    priya.taps_template_button("Shop now", "Shop now")
    assert ok(seller_api.get(url))["stats"]["replied"] == 1
