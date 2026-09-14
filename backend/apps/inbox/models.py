"""Inbox: conversations with contacts, the messages in them, uploaded media and internal notes.

Other apps (campaigns, automations) read these models and FK to ``Message``; writes go through
``apps.inbox.sending`` and ``apps.inbox.services``.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import TenantScopedModel


class Conversation(TenantScopedModel):
    """One thread per (contact, business phone number) in a workspace.

    ``service_window_expires_at`` is 24 hours after the customer's latest message: until then
    free-form messages may be sent; afterwards only approved templates.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING = "pending", "Pending"
        CLOSED = "closed", "Closed"

    contact = models.ForeignKey(
        "contacts.Contact", on_delete=models.CASCADE, related_name="conversations"
    )
    phone_number = models.ForeignKey(
        "whatsapp.PhoneNumber", on_delete=models.CASCADE, related_name="conversations"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_conversations",
    )
    unread_count = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    service_window_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "contact", "phone_number"],
                name="inbox_conversation_unique_contact_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "status", "last_message_at"],
                name="inbox_conv_ws_status_last_idx",
            ),
            models.Index(fields=["workspace", "last_message_at"], name="inbox_conv_ws_last_idx"),
        ]

    def __str__(self) -> str:
        return f"Conversation {self.pk} ({self.status})"


class MediaAsset(TenantScopedModel):
    """A file uploaded by a member to send as a media message.

    ``meta_media_id`` caches the id from Meta's media upload for reuse. Meta media ids belong to
    the phone number they were uploaded to and expire, so reuse checks both.
    """

    file = models.FileField(upload_to="inbox/assets/%Y/%m/")
    mime_type = models.CharField(max_length=128)
    file_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    meta_media_id = models.CharField(max_length=64, blank=True)
    meta_phone_number_id = models.CharField(max_length=64, blank=True)
    meta_uploaded_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        pass

    def __str__(self) -> str:
        return self.file_name or str(self.pk)


class Message(TenantScopedModel):
    """A WhatsApp message in a conversation, inbound or outbound.

    Outbound messages start ``queued``; ``inbox.dispatch_message`` claims them (``sending``) and
    stores the ``wamid`` Meta returns (``sent``). Delivery webhooks move them forward
    monotonically. Inbound messages are ``received`` and never change status.
    """

    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    class Type(models.TextChoices):
        TEXT = "text", "Text"
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"
        DOCUMENT = "document", "Document"
        STICKER = "sticker", "Sticker"
        LOCATION = "location", "Location"
        CONTACTS = "contacts", "Contacts"
        INTERACTIVE = "interactive", "Interactive"
        BUTTON = "button", "Button"
        REACTION = "reaction", "Reaction"
        TEMPLATE = "template", "Template"
        UNSUPPORTED = "unsupported", "Unsupported"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        FAILED = "failed", "Failed"
        RECEIVED = "received", "Received"

    class Source(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        INBOX = "inbox", "Inbox"
        CAMPAIGN = "campaign", "Campaign"
        AUTOMATION = "automation", "Automation"
        API = "api", "API"

    MEDIA_TYPES = frozenset({Type.IMAGE, Type.VIDEO, Type.AUDIO, Type.DOCUMENT, Type.STICKER})

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    direction = models.CharField(max_length=8, choices=Direction.choices)
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.TEXT)
    text = models.TextField(blank=True)
    # Inbound: Meta's raw message object. Outbound: the Cloud API request body without "to".
    payload = models.JSONField(default=dict, blank=True)

    template = models.ForeignKey(
        "message_templates.MessageTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Snapshot at send time: the template may change or be deleted later.
    template_name = models.CharField(max_length=512, blank=True)
    template_language = models.CharField(max_length=16, blank=True)
    template_category = models.CharField(max_length=32, blank=True)
    template_components = models.JSONField(default=list, blank=True)

    wamid = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True)

    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    source = models.CharField(max_length=16, choices=Source.choices)
    source_ref = models.CharField(max_length=255, blank=True, default="")
    # NULL (not "") when absent: the partial unique constraint only covers keys that are set.
    idempotency_key = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001

    reply_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reply_to_wamid = models.CharField(max_length=255, blank=True)

    media_asset = models.ForeignKey(
        MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name="messages"
    )
    media_id = models.CharField(max_length=64, blank=True)  # Meta media id of an inbound file
    mime_type = models.CharField(max_length=128, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    size = models.PositiveBigIntegerField(null=True, blank=True)
    file = models.FileField(upload_to="inbox/media/%Y/%m/", blank=True)

    pricing_category = models.CharField(max_length=32, blank=True)
    billable = models.BooleanField(null=True, blank=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="inbox_message_unique_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "source", "source_ref"], name="inbox_msg_ws_source_ref_idx"
            ),
            models.Index(fields=["conversation", "created_at"], name="inbox_msg_conv_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_direction_display()} {self.type} message {self.pk} ({self.status})"


class ConversationNote(TenantScopedModel):
    """Internal note on a conversation; never sent to the customer."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    body = models.TextField()

    class Meta(TenantScopedModel.Meta):
        pass

    def __str__(self) -> str:
        return f"Note {self.pk} on conversation {self.conversation_id}"
