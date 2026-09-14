"""Demo data for ``manage.py seed_demo``: a completed campaign with realistic stats and a draft.

Idempotent, and makes no Graph calls. The template, tag and contacts are created only if missing.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.contacts import services as contact_services
from apps.contacts.models import Contact, Tag
from apps.message_templates.models import MessageTemplate
from apps.whatsapp.models import PhoneNumber

from . import services
from .models import Campaign, CampaignRecipient

TEMPLATE_NAME = "demo_festive_offer"
TEMPLATE_BODY = "Hi {{1}}, our festive sale is live. Use code {{2}} for 15% off this week."
TAG_NAME = "Festive offers"
COMPLETED_NAME = "Festive sale announcement"
DRAFT_NAME = "Weekend restock alert"
COUPON = "FESTIVE15"

CONTACTS = (
    ("+919000001101", "Aarav Mehta"),
    ("+919000001102", "Ananya Iyer"),
    ("+919000001103", "Rohan Gupta"),
    ("+919000001104", "Priya Nair"),
    ("+919000001105", "Kabir Singh"),
    ("+919000001106", "Meera Joshi"),
    ("+919000001107", "Vikram Rao"),
    ("+919000001108", "Sneha Kulkarni"),
    ("+919000001109", "Arjun Reddy"),
    ("+919000001110", "Isha Kapoor"),
    ("+919000001111", "Farhan Qureshi"),
    ("+919000001112", "Lakshmi Menon"),
)
# Outcome per contact above, in order: status, error code, replied.
OUTCOMES = (
    ("read", "", True),
    ("read", "", True),
    ("read", "", False),
    ("read", "", True),
    ("read", "", False),
    ("read", "", False),
    ("delivered", "", False),
    ("delivered", "", False),
    ("delivered", "", False),
    ("sent", "", False),
    ("failed", services.MARKETING_LIMIT_ERROR, False),
    ("skipped", "", False),
)


def _variable_mapping() -> dict:
    return {
        "body": [
            {"source": "contact_field", "value": "name", "fallback": "there"},
            {"source": "static", "value": COUPON, "fallback": ""},
        ],
        "header": None,
        "buttons": {},
    }


def _template(phone_number: PhoneNumber) -> MessageTemplate:
    template = MessageTemplate.objects.filter(
        waba=phone_number.waba, name=TEMPLATE_NAME, language="en"
    ).first()
    if template is not None:
        return template
    from apps.message_templates.factories import MessageTemplateFactory, standard_components

    return MessageTemplateFactory(
        waba=phone_number.waba,
        workspace=phone_number.workspace,
        name=TEMPLATE_NAME,
        language="en",
        category=MessageTemplate.Category.MARKETING,
        status=MessageTemplate.Status.APPROVED,
        components=standard_components(TEMPLATE_BODY),
    )


def _tag(workspace) -> Tag:
    tag = Tag.objects.filter(workspace=workspace, name__iexact=TAG_NAME).first()
    if tag is not None:
        return tag
    from apps.contacts.factories import TagFactory

    return TagFactory(workspace=workspace, name=TAG_NAME, color="#25D366")


def _contacts(workspace, tag: Tag) -> list[Contact]:
    from apps.contacts.factories import ContactFactory

    contacts = []
    for index, (phone, name) in enumerate(CONTACTS):
        contact = Contact.objects.filter(workspace=workspace, phone_e164=phone).first()
        if contact is None:
            opted_out = OUTCOMES[index][0] == "skipped"
            contact = ContactFactory(
                workspace=workspace,
                phone_e164=phone,
                name=name,
                marketing_opt_in_status=(
                    Contact.OptInStatus.OPTED_OUT if opted_out else Contact.OptInStatus.OPTED_IN
                ),
                opted_in_at=timezone.now() - timedelta(days=30),
                opt_in_source="demo",
            )
        contact_services.add_tags(contact, [tag])
        contacts.append(contact)
    return contacts


def _completed_campaign(workspace, phone_number, template, tag, contacts) -> None:
    if Campaign.objects.filter(workspace=workspace, name=COMPLETED_NAME).exists():
        return
    started = timezone.now() - timedelta(days=3)
    eligible = sum(1 for status, _, _ in OUTCOMES if status != "skipped")
    campaign = Campaign.objects.create(
        workspace=workspace,
        name=COMPLETED_NAME,
        status=Campaign.Status.COMPLETED,
        template=template,
        template_snapshot=services.template_snapshot(template),
        phone_number=phone_number,
        audience={"tag_ids": [str(tag.pk)], "match": "any", "contact_ids": []},
        variable_mapping=_variable_mapping(),
        started_at=started,
        completed_at=started + timedelta(minutes=12),
        consent_attested=True,
        attested_at=started,
        attested_by=workspace.created_by,
        created_by=workspace.created_by,
        estimated_cost=services.estimate_cost(template.category, eligible).quantize(
            Decimal("0.0001")
        ),
    )
    recipients = []
    for contact, (status, error_code, replied) in zip(contacts, OUTCOMES, strict=True):
        reached = status in ("sent", "delivered", "read")
        recipients.append(
            CampaignRecipient(
                workspace=workspace,
                campaign=campaign,
                contact=contact,
                status=status,
                skip_reason=(
                    CampaignRecipient.SkipReason.OPTED_OUT
                    if status == "skipped"
                    else CampaignRecipient.SkipReason.PER_USER_MARKETING_LIMIT
                    if error_code
                    else ""
                ),
                error_code=error_code,
                params={"body": [contact.name, COUPON], "header": None, "buttons": {}},
                consent_status=contact.marketing_opt_in_status,
                consent_opted_in_at=contact.opted_in_at,
                queued_at=started if status != "skipped" else None,
                sent_at=started + timedelta(minutes=1) if reached else None,
                delivered_at=started + timedelta(minutes=2)
                if status in ("delivered", "read")
                else None,
                read_at=started + timedelta(hours=1) if status == "read" else None,
                failed_at=started + timedelta(minutes=1) if status == "failed" else None,
                replied_at=started + timedelta(hours=2) if replied else None,
            )
        )
    CampaignRecipient.objects.bulk_create(recipients)
    services.recompute_stats(campaign.pk)
    Campaign.objects.filter(pk=campaign.pk).update(last_error=services.MARKETING_LIMIT_MESSAGE)


def seed(workspace) -> None:
    phone_number = (
        PhoneNumber.objects.select_related("waba", "workspace")
        .filter(workspace=workspace, is_default=True)
        .first()
    )
    if phone_number is None:
        return
    template = _template(phone_number)
    tag = _tag(workspace)
    contacts = _contacts(workspace, tag)
    _completed_campaign(workspace, phone_number, template, tag, contacts)
    Campaign.objects.get_or_create(
        workspace=workspace,
        name=DRAFT_NAME,
        defaults={
            "status": Campaign.Status.DRAFT,
            "template": template,
            "template_snapshot": services.template_snapshot(template),
            "phone_number": phone_number,
            "audience": {"tag_ids": [str(tag.pk)], "match": "any", "contact_ids": []},
            "variable_mapping": _variable_mapping(),
            "created_by": workspace.created_by,
        },
    )
