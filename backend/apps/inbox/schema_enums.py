"""Contract enum names for the inbox (docs/contracts/wave-2.md).

Plain value tuples, so this module stays import-light and doesn't depend on models. Model
``TextChoices`` must use the same values; common.enum_overrides maps them by value.
"""

CONVERSATION_STATUSES = ("open", "pending", "closed")
MESSAGE_DIRECTIONS = ("inbound", "outbound")
MESSAGE_TYPES = (
    "text",
    "image",
    "video",
    "audio",
    "document",
    "sticker",
    "location",
    "contacts",
    "interactive",
    "button",
    "reaction",
    "template",
    "order",  # wave 3: a native WhatsApp cart (docs/contracts/wave-3-commerce.md)
    "unsupported",
)
MESSAGE_STATUSES = ("queued", "sending", "sent", "delivered", "read", "failed", "received")
MESSAGE_SOURCES = ("inbound", "inbox", "campaign", "automation", "api", "commerce")
SEND_MESSAGE_TYPES = ("text", "template", "media")
MESSAGE_REPLY_KINDS = ("button", "list", "nfm")  # wave 3: Message.reply

ENUM_NAME_OVERRIDES = {
    "ConversationStatusEnum": CONVERSATION_STATUSES,
    "MessageDirectionEnum": MESSAGE_DIRECTIONS,
    "MessageTypeEnum": MESSAGE_TYPES,
    "MessageStatusEnum": MESSAGE_STATUSES,
    "MessageSourceEnum": MESSAGE_SOURCES,
    "SendMessageTypeEnum": SEND_MESSAGE_TYPES,
    "MessageReplyKindEnum": MESSAGE_REPLY_KINDS,
}
