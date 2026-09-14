"""The buyer bot (docs/contracts/wave-3-commerce.md, "Shop").

:func:`handle_inbound` answers an inbound message on the store number: ``upc:shop:*`` replies,
menu keywords, typed quantities and native ``order`` carts. ``chk``/``ord``/``nfm`` replies and
other text are forwarded to ``apps.orders.services``. It runs with the conversation and the
``BotSession`` row locked, re-validates every reply id against current data, and is idempotent
on the message's wamid.

Replies are session messages sent with source ``automation`` and ``source_ref`` ``"shop"``.
Outside the service window (or on any other send policy error) the bot logs and stops.
"""

import logging
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.billing import entitlements
from apps.catalog import services as catalog
from apps.catalog.models import Collection, Product
from apps.inbox import sending
from apps.inbox.models import Conversation, Message
from apps.orders import services as orders
from apps.orders.models import StoreSettings
from apps.whatsapp.models import PhoneNumber
from common.commerce import ReplyId, parse_reply_id

from . import content
from .models import SESSION_TTL_HOURS, BotSession

logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(hours=SESSION_TTL_HOURS)
BOT_SOURCE_REF = "shop"
ORDER_SCOPES = frozenset({"chk", "ord", "nfm"})
QUANTITY_RE = re.compile(r"^\d{1,3}$")
# Wamids already answered, kept in ``BotSession.context`` (webhook retries re-emit events).
HANDLED_KEY = "handled"
HANDLED_LIMIT = 20
_OFFSET_RE = re.compile(r"^\d{1,6}$")


# --- Store --------------------------------------------------------------------------------------


def enabled_store(workspace_id) -> StoreSettings | None:
    """The workspace's store settings when the store is switched on (never creates a row)."""
    return StoreSettings.objects.filter(workspace_id=workspace_id, enabled=True).first()


def is_store_number(store: StoreSettings, phone_number_id) -> bool:
    """Whether ``phone_number_id`` (a ``PhoneNumber`` pk) is the store number: the one chosen in
    settings, else the workspace default number."""
    if phone_number_id is None:
        return False
    if store.phone_number_id:
        return store.phone_number_id == phone_number_id
    return PhoneNumber.objects.filter(
        pk=phone_number_id, workspace_id=store.workspace_id, is_default=True
    ).exists()


def available_store(workspace, phone_number_id=None) -> StoreSettings | None:
    """The store when buyers can shop: enabled, the plan has ``commerce``, the workspace is
    active and (when given) ``phone_number_id`` is the store number."""
    if not workspace.is_active:
        return None
    store = enabled_store(workspace.pk)
    if store is None:
        return None
    if phone_number_id is not None and not is_store_number(store, phone_number_id):
        return None
    if not entitlements.has_feature(workspace, entitlements.COMMERCE):
        return None
    return store


def normalize_text(text: str | None) -> str:
    return " ".join(str(text or "").split()).casefold()


def is_menu_keyword(store: StoreSettings, text: str | None) -> bool:
    """Case-insensitive exact match against ``menu_keywords``."""
    normalized = normalize_text(text)
    if not normalized:
        return False
    keywords = store.menu_keywords if isinstance(store.menu_keywords, list) else []
    return normalized in {normalize_text(k) for k in keywords if isinstance(k, str)}


def is_expired(session: BotSession, now=None) -> bool:
    return session.expires_at is not None and session.expires_at <= (now or timezone.now())


def awaits_quantity(session: BotSession, now=None) -> bool:
    return session.state == BotSession.State.AWAITING_QUANTITY and not is_expired(session, now)


# --- Shared content lookups (bot and automation actions) ----------------------------------------


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _positive_int(value: Any) -> int | None:
    text = str(value)
    if not QUANTITY_RE.fullmatch(text):
        return None
    number = int(text)
    return number if number > 0 else None


def _uncollected_products(workspace):
    return catalog.shoppable_products(workspace).filter(collection__isnull=True)


def _native_catalog(store: StoreSettings, workspace, conversation: Conversation):
    if store.shop_mode != StoreSettings.ShopMode.NATIVE_CATALOG:
        return None
    return catalog.connected_catalog(workspace, conversation.phone_number)


def _synced_skus(queryset, limit: int) -> list[str]:
    return list(
        queryset.filter(meta_sync_status=Product.SyncStatus.SYNCED)
        .order_by("position", "name", "id")
        .values_list("sku", flat=True)[:limit]
    )


def product_page(workspace, key: str, offset: Any):
    """A page of products for ``upc:shop:col:<key>:<offset>``, or None when the collection is
    gone or inactive, the offset is invalid or the page is empty (a stale id)."""
    if not _OFFSET_RE.fullmatch(str(offset)):
        return None
    offset = int(offset)
    if key == content.ALL_PRODUCTS:
        products, has_more = catalog.list_shoppable_products(
            workspace, offset=offset, limit=content.PAGE_SIZE
        )
        title, description = "All products", ""
    elif key == content.OTHER_PRODUCTS:
        rows = list(
            _uncollected_products(workspace).order_by("position", "name", "id")[
                offset : offset + content.PAGE_SIZE + 1
            ]
        )
        products, has_more = rows[: content.PAGE_SIZE], len(rows) > content.PAGE_SIZE
        title, description = "Other products", ""
    else:
        collection_id = _uuid(key)
        collection = (
            Collection.objects.filter(workspace=workspace, pk=collection_id, is_active=True).first()
            if collection_id
            else None
        )
        if collection is None:
            return None
        products, has_more = catalog.list_shoppable_products(
            workspace, collection=collection, offset=offset, limit=content.PAGE_SIZE
        )
        key = str(collection.pk)
        title, description = collection.name, collection.description
    if not products:
        return None
    return content.products_content(
        title=title,
        description=description,
        key=key,
        offset=offset,
        products=products,
        has_more=has_more,
    )


def browse_content(store: StoreSettings, workspace, conversation: Conversation):
    """What *Shop now* sends: the catalog message in native catalog mode, else the collections
    list (or the first product page when the store has no collections). None without products."""
    meta_catalog = _native_catalog(store, workspace, conversation)
    if meta_catalog is not None:
        thumbnail = _synced_skus(catalog.shoppable_products(workspace), 1)
        return content.catalog_content(store, thumbnail_sku=thumbnail[0] if thumbnail else None)
    collections = catalog.list_shoppable_collections(workspace)
    if not collections:
        return product_page(workspace, content.ALL_PRODUCTS, 0)
    return content.collections_content(
        store, collections, has_other=_uncollected_products(workspace).exists()
    )


def collection_content(store: StoreSettings, workspace, conversation, collection: Collection):
    """One collection: a native ``product_list`` of synced products in native catalog mode, else
    the bot product list. None when the collection has nothing to show."""
    meta_catalog = _native_catalog(store, workspace, conversation)
    if meta_catalog is not None:
        skus = _synced_skus(
            catalog.shoppable_products(workspace).filter(collection=collection),
            content.MAX_PRODUCT_LIST_ITEMS,
        )
        if skus:
            return content.product_list_content(meta_catalog.catalog_id, collection.name, skus)
    return product_page(workspace, str(collection.pk), 0)


def parse_native_order(payload: Mapping[str, Any]) -> tuple[list[catalog.CartLine], int | None]:
    """Cart lines from an ``order`` message and the buyer-side total in paise.

    ``item_price`` (rupees) is only a quote shown for comparison: None when any line has no
    valid price. The charge always comes from ``catalog.price_items``.
    """
    order = payload.get("order") if isinstance(payload, Mapping) else None
    items = order.get("product_items") if isinstance(order, Mapping) else None
    lines: list[catalog.CartLine] = []
    quoted: Decimal | None = Decimal(0)
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        sku = str(item.get("product_retailer_id") or "").strip()
        raw_quantity = item.get("quantity")
        quantity = _positive_int(raw_quantity) if not isinstance(raw_quantity, bool) else None
        if not sku or quantity is None:
            continue
        lines.append(catalog.CartLine(quantity=quantity, sku=sku))
        price = _decimal(item.get("item_price"))
        quoted = None if price is None or quoted is None else quoted + price * quantity
    if not lines or quoted is None:
        return lines, None
    return lines, int((quoted * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number >= 0 else None


def reply_id_from_payload(payload: Mapping[str, Any]) -> str | None:
    """The interactive reply id stored in Meta's raw message (when the event didn't carry it)."""
    if not isinstance(payload, Mapping):
        return None
    body = payload.get("interactive")
    if isinstance(body, Mapping):
        for key in ("button_reply", "list_reply"):
            reply = body.get(key)
            if isinstance(reply, Mapping) and reply.get("id"):
                return str(reply["id"])
        nfm = body.get("nfm_reply")
        if body.get("type") == "nfm_reply" and isinstance(nfm, Mapping) and nfm.get("name"):
            return f"upc:nfm:{nfm['name']}"
    button = payload.get("button")
    if isinstance(button, Mapping) and button.get("payload"):
        return str(button["payload"])
    return None


# --- Inbound ------------------------------------------------------------------------------------


def handle_inbound(message_id, *, reply_id: str | None = None) -> bool:
    """Answer an inbound message when the store handles it. Returns True when handled.

    Safe to run repeatedly for the same message: the wamid is remembered on the session.
    """
    message = Message.objects.select_related("workspace").filter(pk=message_id).first()
    if (
        message is None
        or message.direction != Message.Direction.INBOUND
        or message.source != Message.Source.INBOUND
    ):
        return False
    workspace = message.workspace
    with transaction.atomic():
        conversation = (
            Conversation.objects.select_for_update(of=("self",))
            .select_related("contact", "phone_number")
            .get(pk=message.conversation_id)
        )
        store = available_store(workspace, conversation.phone_number_id)
        if store is None:
            return False
        session = _locked_session(conversation)
        context = session.context if isinstance(session.context, dict) else {}
        handled = [marker for marker in context.pop(HANDLED_KEY, []) if isinstance(marker, str)]
        marker = message.wamid or str(message.pk)
        if marker in handled:
            return False

        now = timezone.now()
        if is_expired(session, now):
            session.state = BotSession.State.IDLE
            session.cart = []
            context = {}
        session.context = context

        turn = _Turn(store=store, conversation=conversation, session=session, message=message)
        result = turn.run(
            reply_id if reply_id is not None else reply_id_from_payload(message.payload)
        )

        session.context = {
            **(session.context if isinstance(session.context, dict) else {}),
            HANDLED_KEY: [*handled, marker][-HANDLED_LIMIT:],
        }
        buyer_at = message.sent_at or message.created_at or now
        if session.last_message_at is None or buyer_at > session.last_message_at:
            session.last_message_at = buyer_at
        session.expires_at = session.last_message_at + SESSION_TTL
        session.save()
    return result


def _locked_session(conversation: Conversation) -> BotSession:
    if not BotSession.objects.filter(conversation=conversation).exists():
        try:
            with transaction.atomic():
                BotSession.objects.create(
                    workspace_id=conversation.workspace_id, conversation=conversation
                )
        except IntegrityError:
            pass  # created concurrently
    return BotSession.objects.select_for_update().get(conversation=conversation)


def clear_cart_after_order(*, workspace_id, contact_id, phone_number_id) -> int:
    """Empty the bot cart of the buyer's conversation once an order is confirmed."""
    return BotSession.objects.filter(
        workspace_id=workspace_id,
        conversation__contact_id=contact_id,
        conversation__phone_number_id=phone_number_id,
    ).update(cart=[], updated_at=timezone.now())


@dataclass
class _Turn:
    """Handles one inbound message with the conversation and session locked."""

    store: StoreSettings
    conversation: Conversation
    session: BotSession
    message: Message
    sends: int = 0
    stopped: bool = False

    @property
    def workspace(self):
        return self.message.workspace

    # --- Sending --------------------------------------------------------------------------------

    def send(self, message_content) -> Message | None:
        if self.stopped:
            return None
        key = f"shop:{self.message.pk}:{self.sends}"
        self.sends += 1
        try:
            with transaction.atomic():
                return sending.send_message(
                    workspace=self.workspace,
                    contact=self.conversation.contact,
                    content=message_content,
                    conversation=self.conversation,
                    source=Message.Source.AUTOMATION,
                    source_ref=BOT_SOURCE_REF,
                    idempotency_key=key,
                )
        except sending.SendPolicyError as exc:
            self.stopped = True
            logger.info("Shop reply to message %s not sent (%s)", self.message.pk, exc.default_code)
        return None

    def unavailable(self) -> None:
        self.reset_state()
        self.send(content.menu_content(self.store, notice=content.UNAVAILABLE))

    # --- State ----------------------------------------------------------------------------------

    @property
    def context(self) -> dict:
        if not isinstance(self.session.context, dict):
            self.session.context = {}
        return self.session.context

    def reset_state(self) -> None:
        self.session.state = BotSession.State.IDLE

    def back_id(self) -> str:
        key, offset = self.context.get("collection_key"), self.context.get("offset")
        if isinstance(key, str) and isinstance(offset, int):
            try:
                return content.shop_id("col", key, offset)
            except ValueError:
                pass
        return content.shop_id("browse")

    def cart_lines(self) -> list[catalog.CartLine]:
        lines = []
        for line in self.session.cart if isinstance(self.session.cart, list) else []:
            if not isinstance(line, Mapping):
                continue
            product_id = _uuid(line.get("product_id"))
            quantity = line.get("quantity")
            if (
                product_id
                and isinstance(quantity, int)
                and not isinstance(quantity, bool)
                and quantity > 0
            ):
                lines.append(catalog.CartLine(quantity=quantity, product_id=product_id))
        return lines

    def store_cart(self, lines) -> None:
        self.session.cart = [
            {"product_id": str(line.product_id), "quantity": line.quantity} for line in lines
        ]

    def priced_cart(self):
        """Re-price the cart and keep only what can still be ordered (with capped quantities)."""
        priced = catalog.price_items(self.workspace, self.cart_lines())
        self.session.cart = [
            {"product_id": str(line.product.pk), "quantity": line.quantity} for line in priced.lines
        ]
        return priced

    # --- Routing --------------------------------------------------------------------------------

    def run(self, reply_id: str | None) -> bool:
        reply = parse_reply_id(reply_id)
        if reply is not None:
            return self.on_reply(reply)
        if self.message.type == Message.Type.ORDER:
            self.reset_state()
            return self.on_native_order()
        if self.message.type != Message.Type.TEXT:
            return False
        if is_menu_keyword(self.store, self.message.text):
            self.reset_state()
            self.send(content.menu_content(self.store))
            return True
        if self.session.state == BotSession.State.AWAITING_QUANTITY:
            text = normalize_text(self.message.text)
            if QUANTITY_RE.fullmatch(text):
                return self.on_typed_quantity(int(text))
            self.reset_state()
        return bool(orders.handle_checkout_text(self.message))

    def on_reply(self, reply: ReplyId) -> bool:
        if reply.scope in ORDER_SCOPES:
            self.reset_state()
            if not orders.handle_checkout_reply(self.message, reply):
                self.unavailable()
            return True
        if reply.scope != "shop":
            return False
        action = SHOP_ACTIONS.get(reply.action)
        if action is None or len(reply.args) != action[1]:
            self.unavailable()
            return True
        self.reset_state()
        if not action[0](self, *reply.args):
            self.unavailable()
        return True

    # --- Shop actions (return False for a stale or invalid id) ----------------------------------

    def do_menu(self) -> bool:
        self.send(content.menu_content(self.store))
        return True

    def do_browse(self) -> bool:
        browse = browse_content(self.store, self.workspace, self.conversation)
        self.context.pop("collection_key", None)
        self.context.pop("offset", None)
        self.send(browse if browse is not None else content.no_products_text())
        return True

    def do_col(self, key: str, offset: str) -> bool:
        page = product_page(self.workspace, key, offset)
        if page is None:
            return False
        self.context.update(collection_key=key, offset=int(offset))
        self.send(page)
        return True

    def do_prod(self, product_id: str) -> bool:
        product = catalog.get_shoppable_product(self.workspace, product_id)
        if product is None:
            return False
        self.context["product_id"] = str(product.pk)
        self.send(content.product_card(product, back_id=self.back_id()))
        return True

    def do_qty(self, product_id: str) -> bool:
        product = catalog.get_shoppable_product(self.workspace, product_id)
        cap = content.quantity_cap(product) if product is not None else 0
        if product is None or cap < 1:
            return False
        self.session.state = BotSession.State.AWAITING_QUANTITY
        self.context["product_id"] = str(product.pk)
        self.send(content.quantity_content(product, cap))
        return True

    def do_add(self, product_id: str, quantity: str) -> bool:
        product = catalog.get_shoppable_product(self.workspace, product_id)
        requested = _positive_int(quantity)
        if product is None or requested is None:
            return False
        return self.add_to_cart(product, requested)

    def do_cart(self) -> bool:
        priced = self.priced_cart()
        notes = content.dropped_notes(priced.dropped)
        if priced.is_empty:
            notice = " ".join([*notes, content.EMPTY_CART]) if notes else None
            self.send(content.empty_cart_content(notice))
        else:
            self.send(content.cart_content(priced, notes=notes))
        return True

    def do_clear(self) -> bool:
        self.session.cart = []
        self.send(content.empty_cart_content("Your cart is now empty."))
        return True

    def do_checkout(self) -> bool:
        priced = self.priced_cart()
        if priced.is_empty:
            notice = (
                "The items in your cart are no longer available, so there's nothing to check "
                "out yet."
                if priced.dropped
                else "Your cart is empty, so there's nothing to check out yet."
            )
            self.send(content.empty_cart_content(notice))
            return True
        return self.checkout(priced, source="bot")

    def do_orders(self) -> bool:
        orders.send_recent_orders(self.conversation)
        return True

    def do_talk(self) -> bool:
        self.send(content.support_text(self.store))
        return True

    # --- Helpers --------------------------------------------------------------------------------

    def add_to_cart(self, product: Product, requested: int) -> bool:
        cap = content.quantity_cap(product)
        if cap < 1:
            return False
        lines = self.cart_lines()
        existing = sum(line.quantity for line in lines if line.product_id == product.pk)
        in_cart = min(existing + requested, cap)
        others = [line for line in lines if line.product_id != product.pk]
        self.store_cart([*others, catalog.CartLine(quantity=in_cart, product_id=product.pk)])
        priced = catalog.price_items(self.workspace, self.cart_lines())
        self.send(
            content.added_content(
                product,
                requested=requested,
                added=in_cart - existing,
                in_cart=in_cart,
                cap=cap,
                item_count=priced.item_count,
                subtotal_paise=priced.subtotal_paise,
                back_id=self.back_id(),
            )
        )
        return True

    def on_typed_quantity(self, quantity: int) -> bool:
        product = catalog.get_shoppable_product(self.workspace, self.context.get("product_id"))
        cap = content.quantity_cap(product) if product is not None else 0
        if product is None or cap < 1:
            self.unavailable()
            return True
        if not 1 <= quantity <= cap:
            self.send(content.quantity_retry_text(cap))  # still awaiting a quantity
            return True
        self.reset_state()
        return self.add_to_cart(product, quantity)

    def on_native_order(self) -> bool:
        lines, quoted_total = parse_native_order(self.message.payload)
        priced = catalog.price_items(self.workspace, lines)
        if priced.is_empty:
            self.send(
                content.empty_cart_content(
                    "Sorry, the items in your cart are not available right now."
                )
            )
            return True
        return self.checkout(
            priced,
            source="native_cart",
            source_wamid=self.message.wamid,
            quoted_total_paise=quoted_total,
        )

    def checkout(self, priced, **kwargs) -> bool:
        try:
            with transaction.atomic():
                orders.start_checkout(
                    workspace=self.workspace, conversation=self.conversation, cart=priced, **kwargs
                )
        except catalog.OutOfStock:
            self.send(content.sold_out_content())
        except sending.SendPolicyError as exc:
            logger.info("Checkout for message %s stopped: %s", self.message.pk, exc)
        return True


# action -> (handler, number of reply id arguments)
SHOP_ACTIONS = {
    "menu": (_Turn.do_menu, 0),
    "browse": (_Turn.do_browse, 0),
    "col": (_Turn.do_col, 2),
    "prod": (_Turn.do_prod, 1),
    "add": (_Turn.do_add, 2),
    "qty": (_Turn.do_qty, 1),
    "cart": (_Turn.do_cart, 0),
    "clear": (_Turn.do_clear, 0),
    "checkout": (_Turn.do_checkout, 0),
    "orders": (_Turn.do_orders, 0),
    "talk": (_Turn.do_talk, 0),
}
