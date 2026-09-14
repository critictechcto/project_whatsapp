"""Message content for the buyer bot (docs/contracts/wave-3-commerce.md, "Shop").

Pure builders: they read the objects passed in and return ``apps.inbox.sending`` content for the
bot to send. ``apps.inbox.interactive`` enforces Meta's limits; these builders keep every text
inside them (≤ 10 list rows, row titles ≤ 24, button titles ≤ 20, bodies ≤ 1024).
"""

from collections.abc import Iterable, Sequence

from apps.catalog import services as catalog
from apps.catalog.models import Product
from apps.inbox import interactive
from apps.inbox.interactive import ImageHeader, ListRow, ListSection, ProductSection
from apps.inbox.sending import InteractiveContent, TextContent
from common.commerce import build_reply_id

MENU_FOOTER = "Powered by UpChatz"
PAGE_SIZE = 9  # products per list page; the tenth row is "More products"
MAX_QUANTITY_ROWS = 10
MAX_COLLECTION_ROWS = interactive.MAX_LIST_ROWS
MAX_PRODUCT_LIST_ITEMS = interactive.MAX_PRODUCTS
DESCRIPTION_PREVIEW = 300
CART_NOTES_PREVIEW = 300
ELLIPSIS = "…"

# Pseudo collection keys in ``upc:shop:col:<key>:<offset>``: every product (when the store has no
# collections) and products without a collection.
ALL_PRODUCTS = "all"
OTHER_PRODUCTS = "other"

UNAVAILABLE = "This option is no longer available."
NO_PRODUCTS = "Our store has no products available right now. Please check back soon."
DEFAULT_SUPPORT = "Thanks for reaching out! Someone from our team will reply here soon."
SOLD_OUT = "Sorry, some items in your cart just sold out. Please check your cart and try again."
EMPTY_CART = "Your cart is empty."


def shop_id(action: str, *args: object) -> str:
    """``shop_id("add", product_id, 2)`` → ``"upc:shop:add:<uuid>:2"``."""
    return build_reply_id("shop", action, *args)


def format_inr(paise: int) -> str:
    """``145000`` → ``"₹1,450.00"``, with Indian digit grouping (``₹1,00,000.00``)."""
    sign = "-" if paise < 0 else ""
    rupees, remainder = divmod(abs(int(paise)), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"{sign}₹{digits}.{remainder:02d}"


def clip(text: str | None, limit: int) -> str:
    """``text`` stripped and cut to ``limit`` characters with an ellipsis."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + ELLIPSIS


def one_line(text: str | None, limit: int) -> str:
    return clip(" ".join(str(text or "").split()), limit)


def store_name(store) -> str:
    return one_line(store.store_name, 60) or "our store"


def _footer(store) -> str | None:
    return MENU_FOOTER if store.powered_by_footer else None


def _items(count: int) -> str:
    return f"{count} item" if count == 1 else f"{count} items"


def price_text(product: Product) -> str:
    """The price buyers pay, with the MRP when a sale price applies."""
    price = product.effective_price_paise
    if price < product.price_paise:
        return f"{format_inr(price)} (MRP {format_inr(product.price_paise)})"
    return format_inr(price)


def quantity_cap(product: Product) -> int:
    """Most a buyer can order of ``product``: ``max_qty_per_order`` and tracked stock."""
    cap = product.max_qty_per_order
    if product.stock_qty is not None:
        cap = min(cap, product.stock_qty)
    return max(cap, 0)


# --- Menu and browsing --------------------------------------------------------------------------


def menu_content(store, *, notice: str | None = None) -> InteractiveContent:
    """The welcome menu: *Shop now*, *My orders*, *Talk to us*."""
    body = (store.welcome_message or "").strip() or (
        f"Welcome to {store_name(store)}! Tap *Shop now* to browse our products."
    )
    if notice:
        body = f"{notice}\n\n{body}"
    return interactive.reply_buttons(
        clip(body, interactive.MAX_BODY),
        [
            (shop_id("browse"), "Shop now"),
            (shop_id("orders"), "My orders"),
            (shop_id("talk"), "Talk to us"),
        ],
        footer=_footer(store),
    )


def collections_content(store, collections: Sequence, *, has_other: bool) -> InteractiveContent:
    """A list of collections (≤ 10 rows); "Other products" is the last row when some products
    have no collection."""
    limit = MAX_COLLECTION_ROWS - 1 if has_other else MAX_COLLECTION_ROWS
    rows = [
        ListRow(
            shop_id("col", collection.pk, 0),
            one_line(collection.name, interactive.MAX_ROW_TITLE),
            one_line(collection.description, interactive.MAX_ROW_DESCRIPTION),
        )
        for collection in list(collections)[:limit]
    ]
    if has_other:
        rows.append(ListRow(shop_id("col", OTHER_PRODUCTS, 0), "Other products"))
    return interactive.list_message(
        clip(f"What would you like to shop at {store_name(store)}? Choose a collection.", 1024),
        "View collections",
        [ListSection("Collections", rows)],
    )


def products_content(
    *,
    title: str,
    description: str,
    key: str,
    offset: int,
    products: Sequence[Product],
    has_more: bool,
) -> InteractiveContent:
    """One page of products (9 rows) plus a "More products" row with the next offset."""
    page = list(products)[:PAGE_SIZE]
    rows = [
        ListRow(
            shop_id("prod", product.pk),
            one_line(product.name, interactive.MAX_ROW_TITLE),
            one_line(price_text(product), interactive.MAX_ROW_DESCRIPTION),
        )
        for product in page
    ]
    if has_more:
        rows.append(
            ListRow(shop_id("col", key, offset + len(page)), "More products", "See the next page")
        )
    lines = [f"*{one_line(title, 60)}*"]
    if description.strip():
        lines.append(one_line(description, 200))
    if offset or has_more:
        lines.append(f"Products {offset + 1}-{offset + len(page)}")
    lines.append("Tap *View products* to pick one.")
    return interactive.list_message(
        clip("\n".join(lines), interactive.MAX_BODY),
        "View products",
        [ListSection(one_line(title, interactive.MAX_SECTION_TITLE) or "Products", rows)],
    )


def product_card(product: Product, *, back_id: str) -> InteractiveContent:
    """Image (when public), name, price and a short description with *Add to cart*,
    *Change qty* and *Back*."""
    parts = [f"*{one_line(product.name, 200)}*", price_text(product)]
    description = clip(product.description, DESCRIPTION_PREVIEW)
    body = "\n".join(parts) + (f"\n\n{description}" if description else "")
    image_url = catalog.public_image_url(product)
    header = (
        ImageHeader(image_url)
        if image_url and image_url.startswith(("https://", "http://"))
        else None
    )
    return interactive.reply_buttons(
        clip(body, interactive.MAX_BODY),
        [
            (shop_id("add", product.pk, 1), "Add to cart"),
            (shop_id("qty", product.pk), "Change qty"),
            (back_id, "Back"),
        ],
        header=header,
    )


def quantity_content(product: Product, cap: int) -> InteractiveContent:
    """Quantities 1..min(10, cap) as list rows; larger quantities can be typed."""
    rows = [
        ListRow(
            shop_id("add", product.pk, quantity),
            str(quantity),
            format_inr(product.effective_price_paise * quantity),
        )
        for quantity in range(1, min(cap, MAX_QUANTITY_ROWS) + 1)
    ]
    hint = (
        f"Pick one below or type a number from 1 to {cap}."
        if cap > MAX_QUANTITY_ROWS
        else "Pick one below or type the number."
    )
    body = f"How many *{one_line(product.name, 200)}* would you like? {hint}"
    return interactive.list_message(
        clip(body, interactive.MAX_BODY),
        "Choose quantity",
        [ListSection("Quantity", rows)],
    )


def quantity_retry_text(cap: int) -> TextContent:
    if cap == 1:
        return TextContent("You can order only 1 of this item. Please type 1.")
    return TextContent(f"Please type a number from 1 to {cap}.")


# --- Cart ---------------------------------------------------------------------------------------


def added_content(
    product: Product,
    *,
    requested: int,
    added: int,
    in_cart: int,
    cap: int,
    item_count: int,
    subtotal_paise: int,
    back_id: str,
) -> InteractiveContent:
    """Confirmation after adding, with *Checkout*, *Keep shopping* and *View cart*."""
    name = one_line(product.name, 200)
    if added <= 0:
        first = f"You already have {in_cart} x {name} in your cart, the most you can order."
    else:
        first = f"Added {added} x {name} to your cart."
        if added < requested:
            first += f" You can order at most {cap}."
    body = f"{first}\nCart: {_items(item_count)} · {format_inr(subtotal_paise)}"
    return interactive.reply_buttons(
        clip(body, interactive.MAX_BODY),
        [
            (shop_id("checkout"), "Checkout"),
            (back_id, "Keep shopping"),
            (shop_id("cart"), "View cart"),
        ],
    )


def dropped_notes(dropped: Iterable) -> list[str]:
    """Buyer-facing explanations for ``catalog.DroppedLine`` rows."""
    notes = []
    for line in dropped:
        name = one_line(line.name, 60) or "An item"
        if line.reason == "quantity_capped":
            notes.append(f"Only {line.available} of {name} can be ordered, so we updated it.")
        elif line.reason == "out_of_stock":
            notes.append(f"{name} is out of stock and was removed.")
        else:
            notes.append(f"{name} is no longer available and was removed.")
    return notes


def cart_content(priced, *, notes: Sequence[str] = ()) -> InteractiveContent:
    """Cart lines and subtotal with *Checkout*, *Clear cart* and *Keep shopping*."""
    head = "*Your cart*"
    tail = f"Subtotal: {format_inr(priced.subtotal_paise)}"
    note_text = clip(" ".join(notes), CART_NOTES_PREVIEW)
    if note_text:
        tail = f"{tail}\n\n{note_text}"
    budget = interactive.MAX_BODY - len(head) - len(tail) - 40
    lines: list[str] = []
    for index, line in enumerate(priced.lines):
        text = (
            f"{line.quantity} x {one_line(line.product.name, 60)} — "
            f"{format_inr(line.line_total_paise)}"
        )
        if budget - len(text) - 1 < 0:
            lines.append(f"…and {len(priced.lines) - index} more")
            break
        budget -= len(text) + 1
        lines.append(text)
    body = "\n".join([head, *lines, "", tail])
    return interactive.reply_buttons(
        clip(body, interactive.MAX_BODY),
        [
            (shop_id("checkout"), "Checkout"),
            (shop_id("clear"), "Clear cart"),
            (shop_id("browse"), "Keep shopping"),
        ],
    )


def empty_cart_content(notice: str | None = None) -> InteractiveContent:
    return interactive.reply_buttons(
        clip(notice or EMPTY_CART, interactive.MAX_BODY),
        [(shop_id("browse"), "Shop now"), (shop_id("talk"), "Talk to us")],
    )


def sold_out_content() -> InteractiveContent:
    return interactive.reply_buttons(
        SOLD_OUT, [(shop_id("cart"), "View cart"), (shop_id("browse"), "Keep shopping")]
    )


# --- Native catalog -----------------------------------------------------------------------------


def catalog_content(store, *, thumbnail_sku: str | None = None) -> InteractiveContent:
    body = (
        f"Browse {store_name(store)} in our catalog. Add items to your cart and send it here "
        "to place your order."
    )
    return interactive.catalog_message(
        clip(body, interactive.MAX_BODY), thumbnail_retailer_id=thumbnail_sku, footer=_footer(store)
    )


def product_list_content(catalog_id: str, title: str, skus: Sequence[str]) -> InteractiveContent:
    return interactive.product_list(
        catalog_id,
        one_line(title, interactive.MAX_HEADER) or "Products",
        "Tap a product to see details and add it to your cart.",
        [
            ProductSection(
                one_line(title, interactive.MAX_SECTION_TITLE) or "Products",
                list(skus)[:MAX_PRODUCT_LIST_ITEMS],
            )
        ],
    )


# --- Text replies -------------------------------------------------------------------------------


def support_text(store) -> TextContent:
    return TextContent(clip(store.support_message, 4096) or DEFAULT_SUPPORT)


def no_products_text() -> TextContent:
    return TextContent(NO_PRODUCTS)
