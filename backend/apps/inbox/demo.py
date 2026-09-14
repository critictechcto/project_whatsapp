"""Demo inbox for ``manage.py seed_demo``: a handful of conversations with Indian customers.

Covers inbound and outbound messages in every common status, an assigned conversation, a closed
one, unread messages, an open and an expired service window and a failed send. Rows are written
directly (Meta is never called, nothing is dispatched) and keyed on natural keys, so running the
seeder again changes nothing.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.contacts.models import Contact
from apps.tenants.models import Membership
from apps.whatsapp.models import PhoneNumber
from common.phone import to_wa_id
from common.roles import Role

from .models import Conversation, Message

IN, OUT = Message.Direction.INBOUND, Message.Direction.OUTBOUND
S = Message.Status
OPTED_IN = Contact.OptInStatus.OPTED_IN

# Minutes before "now" at first seed. Each message: (minutes_ago, direction, status, text, extra).
DEMO_CONVERSATIONS = [
    {
        "key": "priya",
        "name": "Priya Sharma",
        "phone": "+919812345601",
        "opt_in": OPTED_IN,
        "assign": True,
        "status": Conversation.Status.OPEN,
        "messages": [
            (95, IN, S.RECEIVED, "Hi, is the blue cotton kurta available in size M?", {}),
            (90, OUT, S.READ, "Yes, it is in stock. Shall I reserve one for you?", {}),
            (25, IN, S.RECEIVED, "Please do. Can I pay cash on delivery?", {}),
            (20, OUT, S.DELIVERED, "Cash on delivery is available for orders up to ₹5,000.", {}),
        ],
    },
    {
        "key": "rahul",
        "name": "Rahul Verma",
        "phone": "+919812345602",
        "opt_in": OPTED_IN,
        "status": Conversation.Status.OPEN,
        "messages": [
            (
                26 * 60,
                OUT,
                S.READ,
                "Hi Rahul, your order UC-10482 has shipped.",
                {
                    "type": Message.Type.TEMPLATE,
                    "template_name": "order_shipped",
                    "template_language": "en",
                    "template_category": "UTILITY",
                    "source": Message.Source.CAMPAIGN,
                    "sent_by_id": None,
                },
            ),
            (12, IN, S.RECEIVED, "When will it reach Pune?", {}),
            (11, IN, S.RECEIVED, "The tracking link is not opening.", {}),
        ],
    },
    {
        "key": "ananya",
        "name": "Ananya Iyer",
        "phone": "+919812345603",
        "opt_in": Contact.OptInStatus.UNKNOWN,
        "status": Conversation.Status.CLOSED,
        "messages": [
            (3 * 24 * 60, IN, S.RECEIVED, "Received the parcel today, thank you!", {}),
            (3 * 24 * 60 - 5, OUT, S.READ, "Glad to hear that, Ananya. Enjoy your purchase!", {}),
        ],
    },
    {
        "key": "mohammed",
        "name": "Mohammed Khan",
        "phone": "+919812345604",
        "opt_in": OPTED_IN,
        "status": Conversation.Status.PENDING,
        "messages": [
            (30 * 60, IN, S.RECEIVED, "Do you deliver to Hyderabad?", {}),
            (
                2 * 60,
                OUT,
                S.FAILED,
                "Yes, we deliver across Telangana in 3 to 5 days.",
                {
                    "error_code": "131047",
                    "error_message": (
                        "More than 24 hours have passed since the customer last replied."
                    ),
                },
            ),
        ],
    },
    {
        "key": "sneha",
        "name": "Sneha Patel",
        "phone": "+919812345605",
        "opt_in": OPTED_IN,
        "status": Conversation.Status.OPEN,
        "messages": [
            (6, IN, S.RECEIVED, "Can I change the delivery address for my order?", {}),
            (4, OUT, S.SENT, "Sure, please share the new address with the PIN code.", {}),
            (1, OUT, S.QUEUED, "We will update it before the order is dispatched.", {}),
        ],
    },
]

SERVICE_WINDOW = timedelta(hours=24)


def seed(workspace) -> None:
    phone_number = (
        PhoneNumber.objects.filter(workspace=workspace)
        .order_by("-is_default", "created_at")
        .first()
    )
    if phone_number is None:
        return
    agent = (
        Membership.objects.filter(workspace=workspace)
        .filter(Q(role=Role.OWNER) | Q(role=Role.ADMIN) | Q(role=Role.AGENT))
        .order_by("created_at")
        .values_list("user", flat=True)
        .first()
    )
    now = timezone.now().replace(microsecond=0)
    for spec in DEMO_CONVERSATIONS:
        _seed_conversation(workspace, phone_number, agent, spec, now)


def _seed_conversation(workspace, phone_number, agent_id, spec: dict, now) -> None:
    contact, _ = Contact.objects.get_or_create(
        workspace=workspace,
        phone_e164=spec["phone"],
        defaults={
            "wa_id": to_wa_id(spec["phone"]),
            "name": spec["name"],
            "marketing_opt_in_status": spec["opt_in"],
            "opted_in_at": now - timedelta(days=30) if spec["opt_in"] == OPTED_IN else None,
            "opt_in_source": "demo" if spec["opt_in"] == OPTED_IN else "",
        },
    )
    conversation, created = Conversation.objects.get_or_create(
        workspace=workspace, contact=contact, phone_number=phone_number
    )
    if not created:
        return

    tag = f"{workspace.pk.hex[:12]}.{spec['key']}"
    last_inbound = None
    unread = 0
    for index, (minutes_ago, direction, status, text, extra) in enumerate(spec["messages"]):
        at = now - timedelta(minutes=minutes_ago)
        message = _message(workspace, conversation, agent_id, tag, index, at, direction, status)
        for field, value in {"text": text, **extra}.items():
            setattr(message, field, value)
        message.save()
        Message.objects.filter(pk=message.pk).update(created_at=at, updated_at=at)
        if direction == IN:
            last_inbound = at
            unread += 1
        else:
            unread = 0

    last_at = now - timedelta(minutes=spec["messages"][-1][0])
    closed = spec["status"] == Conversation.Status.CLOSED
    Conversation.objects.filter(pk=conversation.pk).update(
        status=spec["status"],
        assignee_id=agent_id if spec.get("assign") else None,
        unread_count=0 if closed else unread,
        last_message_at=last_at,
        last_inbound_at=last_inbound,
        service_window_expires_at=last_inbound + SERVICE_WINDOW if last_inbound else None,
        created_at=now - timedelta(minutes=spec["messages"][0][0]),
    )
    if last_inbound:
        Contact.objects.filter(pk=contact.pk, last_inbound_at__isnull=True).update(
            last_inbound_at=last_inbound
        )


def _message(workspace, conversation, agent_id, tag, index, at, direction, status) -> Message:
    message = Message(
        workspace=workspace,
        conversation=conversation,
        direction=direction,
        type=Message.Type.TEXT,
        status=status,
        idempotency_key=f"demo:{tag}:{index}",
    )
    if direction == IN:
        message.source = Message.Source.INBOUND
        message.wamid = f"wamid.demo.{tag}.{index}"
        message.sent_at = at
        return message
    message.source = Message.Source.INBOX
    message.sent_by_id = agent_id
    if status in (S.SENT, S.DELIVERED, S.READ):
        message.wamid = f"wamid.demo.{tag}.{index}"
        message.sent_at = at
    if status in (S.DELIVERED, S.READ):
        message.delivered_at = at + timedelta(seconds=20)
    if status == S.READ:
        message.read_at = at + timedelta(minutes=2)
    if status == S.FAILED:
        message.failed_at = at + timedelta(seconds=5)
    return message
