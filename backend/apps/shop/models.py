"""Shop: the buyer bot's per-conversation state (docs/contracts/wave-3-commerce.md, "Shop")."""

from django.db import models

from common.models import TenantScopedModel

SESSION_TTL_HOURS = 24


class BotSession(TenantScopedModel):
    """One row per conversation.

    - ``cart``: ``[{"product_id": "<uuid>", "quantity": 2}]``, kept on the server in bot mode.
    - ``context``: paging and focus, e.g. ``{"collection_id", "offset", "product_id"}``.
    - ``expires_at``: 24 hours after ``last_message_at`` (the buyer's latest message).
    """

    class State(models.TextChoices):
        IDLE = "idle", "Idle"
        AWAITING_QUANTITY = "awaiting_quantity", "Awaiting quantity"
        AWAITING_TEXT = "awaiting_text", "Awaiting text"

    conversation = models.OneToOneField(
        "inbox.Conversation", on_delete=models.CASCADE, related_name="bot_session"
    )
    state = models.CharField(max_length=24, choices=State.choices, default=State.IDLE)
    cart = models.JSONField(default=list, blank=True)
    context = models.JSONField(default=dict, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        indexes = [
            models.Index(fields=["expires_at"], name="shop_session_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"Bot session for {self.conversation_id} ({self.state})"
