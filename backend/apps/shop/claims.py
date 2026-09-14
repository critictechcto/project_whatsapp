"""The shop's commerce message claimer (docs/contracts/wave-3-commerce.md, "Claiming").

Claims typed store menu keywords and typed quantities while a bot session awaits one, on the store
number of an enabled store whose plan has ``commerce``. Automations skip claimed messages, so the
buyer never gets two replies. It reads only; it never writes or raises for normal input.
"""

from apps.billing import entitlements
from apps.tenants.models import Workspace
from common.events import MessageRecorded

from . import services
from .models import BotSession

INBOUND = "inbound"
TEXT = "text"
MAX_CLAIM_TEXT = 100


def claim_shop_message(event: MessageRecorded) -> bool:
    if event.direction != INBOUND or event.source != INBOUND or event.type != TEXT:
        return False
    text = services.normalize_text(event.text)
    if not text or len(text) > MAX_CLAIM_TEXT:
        return False
    store = services.enabled_store(event.workspace_id)
    if store is None or not services.is_store_number(store, event.phone_number_id):
        return False
    if not services.is_menu_keyword(store, text):
        if not services.QUANTITY_RE.fullmatch(text):
            return False
        session = (
            BotSession.objects.filter(conversation_id=event.conversation_id)
            .only("state", "expires_at")
            .first()
        )
        if session is None or not services.awaits_quantity(session):
            return False
    workspace = Workspace.objects.filter(pk=event.workspace_id, is_active=True).first()
    return workspace is not None and entitlements.has_feature(workspace, entitlements.COMMERCE)
