import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.billing import entitlements
from apps.campaigns.factories import CampaignFactory
from apps.campaigns.models import Campaign, CampaignRecipient
from apps.contacts.factories import ContactFactory, TagFactory
from apps.contacts.models import Contact
from apps.message_templates.factories import MessageTemplateFactory
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.factories import PhoneNumberFactory
from apps.whatsapp.models import WhatsAppBusinessAccount
from common.roles import Role
from common.testing import assert_tenant_isolated

from .conftest import BASE, MAPPING, tag_audience

pytestmark = pytest.mark.django_db


def url(campaign=None, suffix=""):
    return f"{BASE}/{campaign.pk}/{suffix}" if campaign else f"{BASE}/"


def body(template, tag, **overrides):
    data = {
        "name": "Diwali sale",
        "template_id": str(template.pk),
        "audience": tag_audience(tag),
        "variable_mapping": MAPPING,
    }
    data.update(overrides)
    return data


def error(response):
    return response.json()["error"]


def draft(number, template, tag, **fields):
    return CampaignFactory(
        phone_number=number, template=template, audience=tag_audience(tag), **fields
    )


# --- Access ---------------------------------------------------------------------------------------


def test_create_draft_with_default_number(auth_client, user, number, template, tag):
    response = auth_client().post(url(), body(template, tag), format="json")

    assert response.status_code == 201, response.content
    data = response.json()
    assert data["status"] == "draft"
    assert data["phone_number"]["id"] == str(number.pk)
    assert data["template"] == {
        "id": str(template.pk),
        "name": template.name,
        "language": "en",
        "category": "MARKETING",
    }
    assert data["audience"] == tag_audience(tag)
    assert data["stats"]["total"] == 0
    assert data["estimated_cost"] is None
    assert data["consent_attested"] is False
    assert data["created_by"]["id"] == str(user.pk)


def test_roles(auth_client, number, template, tag):
    campaign = draft(number, template, tag)
    viewer = auth_client(Role.VIEWER)
    agent = auth_client(Role.AGENT)

    assert viewer.get(url()).status_code == 200
    assert viewer.get(url(campaign)).status_code == 200
    assert viewer.get(url(campaign, "recipients/")).status_code == 200
    assert viewer.post(url(campaign, "audience-preview/")).status_code == 200

    denied = [
        agent.post(url(), body(template, tag), format="json"),
        agent.patch(url(campaign), {"name": "x"}, format="json"),
        agent.delete(url(campaign)),
        agent.post(url(campaign, "launch/"), {"consent_attested": True}, format="json"),
        agent.post(url(campaign, "pause/")),
        agent.post(url(campaign, "cancel/")),
    ]
    for response in denied:
        assert response.status_code == 403, response.content
        assert error(response)["code"] == "insufficient_role"


def test_tenant_isolation(auth_client, other_workspace, number, template, tag):
    campaign = draft(number, template, tag)
    outsider = auth_client(workspace=other_workspace)

    assert_tenant_isolated(
        outsider, object_id=campaign.pk, list_url=url(), detail_url=url(campaign)
    )
    for suffix in ("recipients/",):
        assert outsider.get(url(campaign, suffix)).status_code == 404
    for suffix in ("audience-preview/", "launch/", "pause/", "resume/", "cancel/"):
        assert outsider.post(url(campaign, suffix), {}, format="json").status_code == 404
    assert outsider.delete(url(campaign)).status_code == 404
    assert Campaign.objects.filter(pk=campaign.pk).exists()

    # Another workspace's template and tag are unknown ids there.
    response = outsider.post(url(), body(template, tag), format="json")
    assert response.status_code == 400
    details = error(response)["details"]
    assert set(details) >= {"template_id", "phone_number_id", "audience"}


def test_list_filters_by_status(auth_client, number, template, tag):
    kept = draft(number, template, tag)
    draft(number, template, tag, status=Campaign.Status.COMPLETED)
    client = auth_client()

    response = client.get(url(), {"status": "draft"})
    assert [item["id"] for item in response.json()["results"]] == [str(kept.pk)]
    assert client.get(url(), {"status": "nope"}).status_code == 400


# --- Validation -----------------------------------------------------------------------------------


def test_create_validation(auth_client, workspace, number, template, tag):
    client = auth_client()
    other_number = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)
    foreign_template = MessageTemplateFactory(
        waba=other_number.waba, status=MessageTemplate.Status.APPROVED
    )
    one_variable = {"body": MAPPING["body"][:1], "header": None, "buttons": {}}
    cases = [
        (body(foreign_template, tag), "template_id"),
        (body(template, tag, phone_number_id=str(uuid.uuid4())), "phone_number_id"),
        (body(template, tag, variable_mapping=one_variable), "variable_mapping"),
        (
            body(
                template,
                tag,
                audience={"tag_ids": [str(uuid.uuid4())], "contact_ids": [str(uuid.uuid4())]},
            ),
            "audience",
        ),
        (
            body(template, tag, scheduled_at=(timezone.now() - timedelta(hours=1)).isoformat()),
            "scheduled_at",
        ),
        (
            body(
                template,
                tag,
                variable_mapping={
                    "body": [{"source": "contact_field", "value": "city"}] * 2,
                },
            ),
            "variable_mapping",
        ),
        (body(template, tag, name="  "), "name"),
    ]
    for data, field in cases:
        response = client.post(url(), data, format="json")
        assert response.status_code == 400, (field, response.content)
        assert error(response)["code"] == "invalid"
        assert field in error(response)["details"], (field, response.json())

    response = client.post(url(), body(template, tag, variable_mapping=one_variable), format="json")
    assert "body" in error(response)["details"]["variable_mapping"]
    assert not Campaign.objects.exists()


def test_create_without_default_number(auth_client, workspace, tag):
    number = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)
    template = MessageTemplateFactory(waba=number.waba, status=MessageTemplate.Status.APPROVED)
    client = auth_client()

    response = client.post(url(), body(template, tag), format="json")
    assert "phone_number_id" in error(response)["details"]

    response = client.post(
        url(), body(template, tag, phone_number_id=str(number.pk)), format="json"
    )
    assert response.status_code == 201, response.content


def test_patch_draft(auth_client, number, template, tag, make_contact):
    campaign = draft(number, template, tag)
    contact = make_contact(tagged=False)

    response = auth_client().patch(
        url(campaign),
        {"name": "Updated", "audience": {"contact_ids": [str(contact.pk)]}},
        format="json",
    )

    assert response.status_code == 200, response.content
    campaign.refresh_from_db()
    assert campaign.name == "Updated"
    assert campaign.audience == {"tag_ids": [], "match": "any", "contact_ids": [str(contact.pk)]}
    assert campaign.variable_mapping == MAPPING
    assert not CampaignRecipient.objects.exists()  # drafts don't materialise recipients


def test_only_draft_and_scheduled_are_editable(auth_client, number, template, tag):
    client = auth_client()
    for status in ("running", "paused", "completed", "cancelled", "failed"):
        campaign = draft(number, template, tag, status=status)
        response = client.patch(url(campaign), {"name": "x"}, format="json")
        assert response.status_code == 409
        assert error(response)["code"] == "campaign_not_editable"


def test_patch_scheduled_rematerialises_recipients(auth_client, launched, make_contact):
    later = timezone.now() + timedelta(hours=2)
    campaign, _ = launched(2, scheduled_at=later)
    assert campaign.status == Campaign.Status.SCHEDULED
    make_contact()
    client = auth_client()

    response = client.patch(url(campaign), {"audience": campaign.audience}, format="json")

    assert response.status_code == 200, response.content
    assert response.json()["stats"]["total"] == 3
    assert CampaignRecipient.objects.filter(campaign=campaign, status="pending").count() == 3
    assert Decimal(response.json()["estimated_cost"]["amount"]) == Decimal("2.3538")

    past = (timezone.now() - timedelta(minutes=1)).isoformat()
    response = client.patch(url(campaign), {"scheduled_at": past}, format="json")
    assert response.status_code == 400
    response = client.patch(url(campaign), {"scheduled_at": None}, format="json")
    assert response.status_code == 400


def test_delete_only_drafts(auth_client, number, template, tag):
    client = auth_client()
    running = draft(number, template, tag, status=Campaign.Status.RUNNING)
    response = client.delete(url(running))
    assert response.status_code == 409
    assert error(response)["code"] == "campaign_not_editable"

    campaign = draft(number, template, tag)
    assert client.delete(url(campaign)).status_code == 204
    assert not Campaign.objects.filter(pk=campaign.pk).exists()


# --- Audience preview -----------------------------------------------------------------------------


def test_audience_preview_counts(auth_client, number, template, tag, make_contact):
    first = make_contact()
    make_contact()
    make_contact(Contact.OptInStatus.OPTED_OUT)
    make_contact(Contact.OptInStatus.UNKNOWN)
    make_contact(wa_id="")
    extra = make_contact(tagged=False)
    make_contact(tagged=False)  # outside the audience
    campaign = draft(number, template, tag)
    campaign.audience["contact_ids"] = [str(extra.pk), str(first.pk)]
    campaign.save()

    response = auth_client().post(url(campaign, "audience-preview/"))

    assert response.status_code == 200
    assert response.json() == {
        "total": 6,
        "eligible": 3,
        "skipped": {"opted_out": 1, "not_opted_in": 1, "invalid": 1},
    }


def test_audience_preview_missing_variables_and_utility_templates(
    auth_client, number, tag, make_contact
):
    template = MessageTemplateFactory(
        waba=number.waba, status=MessageTemplate.Status.APPROVED
    )  # UTILITY: no marketing opt-in needed
    make_contact(Contact.OptInStatus.UNKNOWN, attributes={"order": "A-1"})
    make_contact(attributes={})
    mapping = {
        "body": [
            {"source": "contact_field", "value": "name", "fallback": "there"},
            {"source": "attribute", "value": "order", "fallback": ""},
        ],
        "header": None,
        "buttons": {},
    }
    campaign = draft(number, template, tag, variable_mapping=mapping)

    response = auth_client().post(url(campaign, "audience-preview/"))

    assert response.json() == {
        "total": 2,
        "eligible": 1,
        "skipped": {"opted_out": 0, "not_opted_in": 0, "invalid": 1},
    }


def test_audience_match_all(auth_client, workspace, number, template, tag, make_contact):
    second = TagFactory(workspace=workspace)
    both = make_contact()
    both.tags.add(second)
    make_contact()
    ContactFactory(
        workspace=workspace,
        marketing_opt_in_status=Contact.OptInStatus.OPTED_IN,
        tags=[second],
    )
    campaign = draft(number, template, tag)
    campaign.audience = tag_audience(tag, second, match="all")
    campaign.save()
    client = auth_client()

    assert client.post(url(campaign, "audience-preview/")).json()["total"] == 1
    campaign.audience["match"] = "any"
    campaign.save()
    assert client.post(url(campaign, "audience-preview/")).json()["total"] == 3


# --- Launch ---------------------------------------------------------------------------------------


def test_launch_now(auth_client, user, number, template, tag, make_contact, commit, fake_graph):
    make_contact()
    make_contact()
    make_contact(Contact.OptInStatus.OPTED_OUT)
    campaign = draft(number, template, tag)

    with commit():
        response = auth_client().post(
            url(campaign, "launch/"), {"consent_attested": True}, format="json"
        )

    assert response.status_code == 200, response.content
    data = response.json()
    assert data["status"] == "running"
    assert data["consent_attested"] is True
    assert data["started_at"] is not None
    assert data["stats"]["total"] == 3
    assert data["stats"]["skipped"] == 1
    assert data["estimated_cost"]["currency"] == "INR"
    assert Decimal(data["estimated_cost"]["amount"]) == Decimal("1.5692")
    assert "Meta" in data["estimated_cost"]["note"]

    campaign.refresh_from_db()
    assert campaign.attested_by == user
    assert campaign.attested_at is not None
    assert len(fake_graph.calls_to("send_message")) == 2
    assert campaign.status == Campaign.Status.COMPLETED
    assert campaign.stats["sent"] == 2


def test_launch_requires_consent(auth_client, number, template, tag, make_contact):
    make_contact()
    campaign = draft(number, template, tag)
    client = auth_client()

    for data in ({}, {"consent_attested": False}):
        response = client.post(url(campaign, "launch/"), data, format="json")
        assert response.status_code == 400
        assert "consent_attested" in error(response)["details"]
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.DRAFT
    assert not CampaignRecipient.objects.exists()


def test_launch_requires_approved_template(auth_client, number, template, tag, make_contact):
    make_contact()
    campaign = draft(number, template, tag)
    MessageTemplate.objects.filter(pk=template.pk).update(status=MessageTemplate.Status.PENDING)

    response = auth_client().post(
        url(campaign, "launch/"), {"consent_attested": True}, format="json"
    )

    assert response.status_code == 409
    assert error(response)["code"] == "template_not_approved"


def test_launch_requires_connected_whatsapp(auth_client, number, template, tag, make_contact):
    make_contact()
    campaign = draft(number, template, tag)
    WhatsAppBusinessAccount.objects.filter(pk=number.waba_id).update(
        status=WhatsAppBusinessAccount.Status.DISCONNECTED
    )

    response = auth_client().post(
        url(campaign, "launch/"), {"consent_attested": True}, format="json"
    )

    assert response.status_code == 409
    assert error(response)["code"] == "whatsapp_not_connected"


def test_launch_rejects_empty_or_ineligible_audience(
    auth_client, number, template, tag, make_contact
):
    client = auth_client()
    empty = CampaignFactory(phone_number=number, template=template)
    response = client.post(url(empty, "launch/"), {"consent_attested": True}, format="json")
    assert response.status_code == 400
    assert "audience" in error(response)["details"]

    make_contact(Contact.OptInStatus.OPTED_OUT)
    ineligible = draft(number, template, tag)
    response = client.post(url(ineligible, "launch/"), {"consent_attested": True}, format="json")
    assert response.status_code == 400
    assert "audience" in error(response)["details"]
    assert not CampaignRecipient.objects.exists()


def test_launch_only_drafts(auth_client, number, template, tag):
    campaign = draft(number, template, tag, status=Campaign.Status.RUNNING)

    response = auth_client().post(
        url(campaign, "launch/"), {"consent_attested": True}, format="json"
    )

    assert response.status_code == 409
    assert error(response)["code"] == "invalid_campaign_transition"


def test_launch_in_the_future_schedules(auth_client, number, template, tag, make_contact):
    make_contact()
    campaign = draft(number, template, tag)
    later = timezone.now() + timedelta(hours=3)

    response = auth_client().post(
        url(campaign, "launch/"),
        {"consent_attested": True, "scheduled_at": later.isoformat()},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "scheduled"
    campaign.refresh_from_db()
    assert campaign.scheduled_at == later
    assert campaign.started_at is None
    assert CampaignRecipient.objects.filter(campaign=campaign, status="pending").count() == 1


def test_scheduling_needs_the_plan_feature(
    auth_client, number, template, tag, make_contact, monkeypatch
):
    make_contact()
    monkeypatch.setattr(entitlements, "has_feature", lambda workspace, feature: False)
    later = (timezone.now() + timedelta(hours=3)).isoformat()
    client = auth_client()
    campaign = draft(number, template, tag)

    response = client.post(
        url(campaign, "launch/"), {"consent_attested": True, "scheduled_at": later}, format="json"
    )
    assert response.status_code == 409
    assert error(response)["code"] == "feature_not_available"
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.DRAFT
    assert not CampaignRecipient.objects.exists()

    response = client.post(
        url(campaign, "launch/"), {"consent_attested": True, "scheduled_at": None}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "running"


# --- Transitions ----------------------------------------------------------------------------------


def test_pause_resume_cancel(auth_client, launched, fake_graph):
    campaign, _ = launched(3)
    client = auth_client()

    def post(action):
        return client.post(url(campaign, f"{action}/"))

    assert post("pause").json()["status"] == "paused"
    response = post("pause")
    assert response.status_code == 409
    assert error(response)["code"] == "invalid_campaign_transition"

    assert post("resume").json()["status"] == "running"
    assert post("resume").status_code == 409

    response = post("cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"
    assert data["stats"]["skipped"] == 3
    reasons = set(
        CampaignRecipient.objects.filter(campaign=campaign).values_list("status", "skip_reason")
    )
    assert reasons == {("skipped", "cancelled")}

    for action in ("pause", "resume", "cancel"):
        assert post(action).status_code == 409
    assert fake_graph.calls_to("send_message") == []


def test_draft_transitions_are_invalid(auth_client, number, template, tag):
    campaign = draft(number, template, tag)
    client = auth_client()

    for action in ("pause", "resume", "cancel"):
        response = client.post(url(campaign, f"{action}/"))
        assert response.status_code == 409
        assert error(response)["code"] == "invalid_campaign_transition"


def test_resume_scheduled_campaign_returns_to_scheduled(auth_client, launched):
    campaign, _ = launched(1, scheduled_at=timezone.now() + timedelta(hours=1))
    client = auth_client()

    assert client.post(url(campaign, "pause/")).json()["status"] == "paused"
    assert client.post(url(campaign, "resume/")).json()["status"] == "scheduled"


def test_resume_requires_approved_template(auth_client, launched, template):
    campaign, _ = launched(1)
    client = auth_client()
    client.post(url(campaign, "pause/"))
    MessageTemplate.objects.filter(pk=template.pk).update(status=MessageTemplate.Status.DISABLED)

    response = client.post(url(campaign, "resume/"))

    assert response.status_code == 409
    assert error(response)["code"] == "template_not_approved"


def test_recipients_list(auth_client, launched, make_contact):
    opted_out = make_contact(Contact.OptInStatus.OPTED_OUT)
    campaign, _ = launched(2)
    client = auth_client()

    response = client.get(url(campaign, "recipients/"))
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3

    response = client.get(url(campaign, "recipients/"), {"status": "skipped"})
    [item] = response.json()["results"]
    assert item["contact"]["id"] == str(opted_out.pk)
    assert item["skip_reason"] == "opted_out"
    assert item["message_id"] is None

    assert client.get(url(campaign, "recipients/"), {"status": "bogus"}).status_code == 400
