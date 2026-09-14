"""Builders for Cloud API interactive messages (docs/contracts/wave-3-commerce.md).

Each builder validates Meta's limits and returns an :class:`~apps.inbox.sending.InteractiveContent`
to pass to ``sending.send_message``. Invalid input raises :class:`InvalidInteractiveContent` (a
``ValueError``) before anything is stored. Interactive messages are session messages: outside the
24-hour customer service window ``send_message`` raises ``OutsideServiceWindow``.

Other apps may import this module (``apps.inbox.interactive``).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .sending import InteractiveContent

__all__ = (
    "ImageHeader",
    "InvalidInteractiveContent",
    "ListRow",
    "ListSection",
    "ProductSection",
    "address_message",
    "catalog_message",
    "cta_url",
    "list_message",
    "product",
    "product_list",
    "reply_buttons",
)

MAX_BODY = 1024
MAX_FOOTER = 60
MAX_HEADER = 60
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
MAX_BUTTON_ID = 256
MAX_LIST_BUTTON = 20
MAX_LIST_ROWS = 10
MAX_LIST_SECTIONS = 10
MAX_SECTION_TITLE = 24
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72
MAX_ROW_ID = 200
MAX_CTA_DISPLAY_TEXT = 20
MAX_URL = 2000
MAX_PRODUCT_SECTIONS = 10
MAX_PRODUCTS = 30
MAX_RETAILER_ID = 100
ADDRESS_COUNTRY = "IN"


class InvalidInteractiveContent(ValueError):
    """The interactive message breaks one of Meta's rules (lengths, counts, required parts)."""


@dataclass(frozen=True, slots=True)
class ImageHeader:
    """An image header; ``url`` must be a public https link Meta can download."""

    url: str


@dataclass(frozen=True, slots=True)
class ListRow:
    id: str
    title: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class ListSection:
    title: str
    rows: Sequence[ListRow]


@dataclass(frozen=True, slots=True)
class ProductSection:
    title: str
    retailer_ids: Sequence[str]


# --- Validation helpers -------------------------------------------------------------------------


def _text(value: Any, label: str, max_length: int, *, required: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise InvalidInteractiveContent(f"The {label} must be text.")
    if required and not value.strip():
        raise InvalidInteractiveContent(f"The {label} may not be blank.")
    if len(value) > max_length:
        raise InvalidInteractiveContent(
            f"The {label} may have at most {max_length} characters ({len(value)} given)."
        )
    return value


def _https_url(value: Any, label: str) -> str:
    url = _text(value, label, MAX_URL)
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise InvalidInteractiveContent(f"The {label} must be an http(s) URL.")
    return url


def _body(body: Any) -> dict[str, str]:
    return {"text": _text(body, "body", MAX_BODY)}


def _add_footer(interactive: dict[str, Any], footer: Any) -> None:
    if footer is not None and footer != "":
        interactive["footer"] = {"text": _text(footer, "footer", MAX_FOOTER)}


def _header(header: str | ImageHeader | None) -> dict[str, Any] | None:
    if header is None or header == "":
        return None
    if isinstance(header, ImageHeader):
        return {"type": "image", "image": {"link": _https_url(header.url, "header image URL")}}
    return {"type": "text", "text": _text(header, "header", MAX_HEADER)}


def _ordered(interactive: dict[str, Any], header: dict[str, Any] | None) -> dict[str, Any]:
    """Put ``header`` right after ``type`` (key order only matters for readability)."""
    if header is None:
        return interactive
    return {"type": interactive["type"], "header": header, **interactive}


def _unique(ids: Sequence[str], label: str) -> None:
    if len(set(ids)) != len(ids):
        raise InvalidInteractiveContent(f"Every {label} id must be unique.")


# --- Builders -----------------------------------------------------------------------------------


def reply_buttons(
    body: str,
    buttons: Sequence[tuple[str, str]],
    *,
    header: str | ImageHeader | None = None,
    footer: str | None = None,
) -> InteractiveContent:
    """1 to 3 quick-reply buttons given as ``(id, title)``; titles ≤ 20, ids ≤ 256 and unique."""
    if not isinstance(buttons, Sequence) or isinstance(buttons, str):
        raise InvalidInteractiveContent("Buttons must be a list of (id, title) pairs.")
    if not 1 <= len(buttons) <= MAX_BUTTONS:
        raise InvalidInteractiveContent(f"Use 1 to {MAX_BUTTONS} reply buttons.")
    items = []
    for button in buttons:
        if not isinstance(button, tuple | list) or len(button) != 2:
            raise InvalidInteractiveContent("Each button must be an (id, title) pair.")
        button_id = _text(button[0], "button id", MAX_BUTTON_ID)
        title = _text(button[1], "button title", MAX_BUTTON_TITLE)
        items.append({"type": "reply", "reply": {"id": button_id, "title": title}})
    _unique([item["reply"]["id"] for item in items], "button")
    interactive: dict[str, Any] = {
        "type": "button",
        "body": _body(body),
        "action": {"buttons": items},
    }
    _add_footer(interactive, footer)
    return InteractiveContent(_ordered(interactive, _header(header)), summary=body)


def list_message(
    body: str,
    button: str,
    sections: Sequence[ListSection],
    *,
    header: str | None = None,
    footer: str | None = None,
) -> InteractiveContent:
    """A list opened by ``button`` (≤ 20): ≤ 10 rows in total, row titles ≤ 24, descriptions
    ≤ 72, row ids ≤ 200 and unique. Section titles (≤ 24) are required with several sections."""
    if isinstance(header, ImageHeader):
        raise InvalidInteractiveContent("A list message header must be text.")
    if not isinstance(sections, Sequence) or not sections:
        raise InvalidInteractiveContent("A list message needs at least one section.")
    if len(sections) > MAX_LIST_SECTIONS:
        raise InvalidInteractiveContent(
            f"A list message may have at most {MAX_LIST_SECTIONS} sections."
        )
    several = len(sections) > 1
    built_sections = []
    row_ids: list[str] = []
    for section in sections:
        if not isinstance(section, ListSection):
            raise InvalidInteractiveContent("Sections must be ListSection objects.")
        if not section.rows:
            raise InvalidInteractiveContent("Every list section needs at least one row.")
        rows = []
        for row in section.rows:
            if not isinstance(row, ListRow):
                raise InvalidInteractiveContent("Rows must be ListRow objects.")
            item = {
                "id": _text(row.id, "row id", MAX_ROW_ID),
                "title": _text(row.title, "row title", MAX_ROW_TITLE),
            }
            if row.description:
                item["description"] = _text(row.description, "row description", MAX_ROW_DESCRIPTION)
            rows.append(item)
            row_ids.append(item["id"])
        built: dict[str, Any] = {}
        title = _text(section.title, "section title", MAX_SECTION_TITLE, required=several)
        if title:
            built["title"] = title
        built["rows"] = rows
        built_sections.append(built)
    if len(row_ids) > MAX_LIST_ROWS:
        raise InvalidInteractiveContent(
            f"A list message may have at most {MAX_LIST_ROWS} rows in total ({len(row_ids)} given)."
        )
    _unique(row_ids, "row")
    interactive: dict[str, Any] = {
        "type": "list",
        "body": _body(body),
        "action": {
            "button": _text(button, "list button", MAX_LIST_BUTTON),
            "sections": built_sections,
        },
    }
    _add_footer(interactive, footer)
    return InteractiveContent(_ordered(interactive, _header(header)), summary=body)


def cta_url(
    body: str,
    display_text: str,
    url: str,
    *,
    header: str | ImageHeader | None = None,
    footer: str | None = None,
) -> InteractiveContent:
    """A call-to-action button (``display_text`` ≤ 20) that opens ``url``."""
    interactive: dict[str, Any] = {
        "type": "cta_url",
        "body": _body(body),
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": _text(display_text, "button text", MAX_CTA_DISPLAY_TEXT),
                "url": _https_url(url, "URL"),
            },
        },
    }
    _add_footer(interactive, footer)
    return InteractiveContent(_ordered(interactive, _header(header)), summary=body)


def _retailer_id(value: Any) -> str:
    return _text(value, "product retailer id", MAX_RETAILER_ID)


def _catalog_id(value: Any) -> str:
    return _text(value, "catalog id", MAX_RETAILER_ID)


def product(
    catalog_id: str,
    retailer_id: str,
    *,
    body: str | None = None,
    footer: str | None = None,
) -> InteractiveContent:
    """A single product card from the connected Meta catalog (``retailer_id`` is the SKU)."""
    interactive: dict[str, Any] = {"type": "product"}
    if body is not None and body != "":
        interactive["body"] = _body(body)
    _add_footer(interactive, footer)
    sku = _retailer_id(retailer_id)
    interactive["action"] = {
        "catalog_id": _catalog_id(catalog_id),
        "product_retailer_id": sku,
    }
    return InteractiveContent(interactive, summary=body or f"Product {sku}")


def product_list(
    catalog_id: str,
    header: str,
    body: str,
    sections: Sequence[ProductSection],
    *,
    footer: str | None = None,
) -> InteractiveContent:
    """Up to 30 products in ≤ 10 titled sections; ``header`` (text, ≤ 60) is required."""
    if not isinstance(sections, Sequence) or not sections:
        raise InvalidInteractiveContent("A product list needs at least one section.")
    if len(sections) > MAX_PRODUCT_SECTIONS:
        raise InvalidInteractiveContent(
            f"A product list may have at most {MAX_PRODUCT_SECTIONS} sections."
        )
    built_sections = []
    total = 0
    for section in sections:
        if not isinstance(section, ProductSection):
            raise InvalidInteractiveContent("Sections must be ProductSection objects.")
        if isinstance(section.retailer_ids, str) or not section.retailer_ids:
            raise InvalidInteractiveContent("Every product section needs at least one product.")
        items = [{"product_retailer_id": _retailer_id(sku)} for sku in section.retailer_ids]
        total += len(items)
        built_sections.append(
            {
                "title": _text(section.title, "section title", MAX_SECTION_TITLE),
                "product_items": items,
            }
        )
    if total > MAX_PRODUCTS:
        raise InvalidInteractiveContent(
            f"A product list may have at most {MAX_PRODUCTS} products ({total} given)."
        )
    interactive: dict[str, Any] = {
        "type": "product_list",
        "header": {"type": "text", "text": _text(header, "header", MAX_HEADER)},
        "body": _body(body),
    }
    _add_footer(interactive, footer)
    interactive["action"] = {"catalog_id": _catalog_id(catalog_id), "sections": built_sections}
    return InteractiveContent(interactive, summary=body)


def catalog_message(
    body: str,
    *,
    thumbnail_retailer_id: str | None = None,
    footer: str | None = None,
) -> InteractiveContent:
    """A "View catalog" button for the number's connected catalog."""
    action: dict[str, Any] = {"name": "catalog_message"}
    if thumbnail_retailer_id:
        action["parameters"] = {
            "thumbnail_product_retailer_id": _retailer_id(thumbnail_retailer_id)
        }
    interactive: dict[str, Any] = {"type": "catalog_message", "body": _body(body)}
    _add_footer(interactive, footer)
    interactive["action"] = action
    return InteractiveContent(interactive, summary=body)


def _string_map(value: Mapping[str, str] | None, label: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise InvalidInteractiveContent(f"The address {label} must be a mapping of strings.")
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, str):
            raise InvalidInteractiveContent(f"The address {label} must be a mapping of strings.")
        result[key] = item
    return result or None


def address_message(
    body: str,
    *,
    values: Mapping[str, str] | None = None,
    validation_errors: Mapping[str, str] | None = None,
) -> InteractiveContent:
    """Ask for a delivery address in India with WhatsApp's native address form.

    ``values`` prefills fields (``name``, ``phone_number``, ``in_pin_code``, ``house_number``,
    ``floor_number``, ``tower_number``, ``building_name``, ``address``, ``landmark_area``,
    ``city``, ``state``); ``validation_errors`` shows a message next to fields to fix. Clients
    that can't show the form fail the message with Meta error 1026.
    """
    parameters: dict[str, Any] = {"country": ADDRESS_COUNTRY}
    prefilled = _string_map(values, "values")
    if prefilled:
        parameters["values"] = prefilled
    errors = _string_map(validation_errors, "validation errors")
    if errors:
        parameters["validation_errors"] = errors
    interactive = {
        "type": "address_message",
        "body": _body(body),
        "action": {"name": "address_message", "parameters": parameters},
    }
    return InteractiveContent(interactive, summary=body)
