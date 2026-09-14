"""Interactive message builders: Cloud API shapes and Meta's limits."""

import pytest

from apps.inbox import interactive
from apps.inbox.interactive import (
    ImageHeader,
    InvalidInteractiveContent,
    ListRow,
    ListSection,
    ProductSection,
)
from apps.inbox.sending import InteractiveContent
from common.commerce import build_reply_id


def rows(count: int, prefix: str = "row") -> list[ListRow]:
    return [ListRow(id=f"{prefix}-{index}", title=f"Item {index}") for index in range(count)]


def test_invalid_content_is_a_value_error():
    assert issubclass(InvalidInteractiveContent, ValueError)


# --- reply_buttons ------------------------------------------------------------------------------


def test_reply_buttons_shape():
    content = interactive.reply_buttons(
        "Your cart total is ₹1,450.",
        [(build_reply_id("chk", "confirm", "o1"), "Confirm"), ("upc:shop:cart", "View cart")],
        header="Sharma Sweets",
        footer="Prices include GST",
    )

    assert isinstance(content, InteractiveContent)
    assert content.summary == "Your cart total is ₹1,450."
    assert content.interactive == {
        "type": "button",
        "header": {"type": "text", "text": "Sharma Sweets"},
        "body": {"text": "Your cart total is ₹1,450."},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": "upc:chk:confirm:o1", "title": "Confirm"}},
                {"type": "reply", "reply": {"id": "upc:shop:cart", "title": "View cart"}},
            ]
        },
        "footer": {"text": "Prices include GST"},
    }


def test_reply_buttons_image_header_and_no_footer():
    content = interactive.reply_buttons(
        "Kaju katli, 500 g", [("add", "Add to cart")], header=ImageHeader("https://cdn.test/k.jpg")
    )

    assert content.interactive["header"] == {
        "type": "image",
        "image": {"link": "https://cdn.test/k.jpg"},
    }
    assert "footer" not in content.interactive


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"buttons": []}, "1 to 3"),
        ({"buttons": [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")]}, "1 to 3"),
        ({"buttons": [("a", "A"), ("a", "B")]}, "unique"),
        ({"buttons": [("a", "x" * 21)]}, "button title"),
        ({"buttons": [("a", " ")]}, "button title"),
        ({"buttons": [("x" * 257, "A")]}, "button id"),
        ({"buttons": [("", "A")]}, "button id"),
        ({"buttons": [("a",)]}, "pair"),
        ({"buttons": "ab"}, "list"),
        ({"body": ""}, "body"),
        ({"body": "   "}, "body"),
        ({"body": "x" * 1025}, "body"),
        ({"footer": "x" * 61}, "footer"),
        ({"header": "x" * 61}, "header"),
        ({"header": ImageHeader("ftp://files.test/a.jpg")}, "URL"),
    ],
)
def test_reply_buttons_limits(kwargs, message):
    arguments = {"body": "Hello", "buttons": [("a", "A")], **kwargs}

    with pytest.raises(InvalidInteractiveContent, match=message):
        interactive.reply_buttons(arguments.pop("body"), arguments.pop("buttons"), **arguments)


def test_reply_buttons_accept_the_maximums():
    content = interactive.reply_buttons(
        "x" * 1024,
        [("a" * 256, "t" * 20), ("b", "B"), ("c", "C")],
        header="h" * 60,
        footer="f" * 60,
    )

    assert len(content.interactive["action"]["buttons"]) == 3


# --- list_message -------------------------------------------------------------------------------


def test_list_message_shape():
    content = interactive.list_message(
        "Pick a collection",
        "Browse",
        [
            ListSection(
                "Sweets",
                [
                    ListRow("upc:shop:col:c1:0", "Mithai", "Kaju katli, laddoo and more"),
                    ListRow("upc:shop:col:c2:0", "Dry fruits"),
                ],
            )
        ],
        header="Sharma Sweets",
        footer="Tap to browse",
    )

    assert content.summary == "Pick a collection"
    assert content.interactive == {
        "type": "list",
        "header": {"type": "text", "text": "Sharma Sweets"},
        "body": {"text": "Pick a collection"},
        "action": {
            "button": "Browse",
            "sections": [
                {
                    "title": "Sweets",
                    "rows": [
                        {
                            "id": "upc:shop:col:c1:0",
                            "title": "Mithai",
                            "description": "Kaju katli, laddoo and more",
                        },
                        {"id": "upc:shop:col:c2:0", "title": "Dry fruits"},
                    ],
                }
            ],
        },
        "footer": {"text": "Tap to browse"},
    }


def test_single_list_section_may_have_no_title():
    content = interactive.list_message("Pick", "Open", [ListSection("", rows(2))])

    assert content.interactive["action"]["sections"] == [
        {"rows": [{"id": "row-0", "title": "Item 0"}, {"id": "row-1", "title": "Item 1"}]}
    ]


def test_list_message_allows_ten_rows_across_sections():
    content = interactive.list_message(
        "Pick", "Open", [ListSection("A", rows(6, "a")), ListSection("B", rows(4, "b"))]
    )

    assert sum(len(s["rows"]) for s in content.interactive["action"]["sections"]) == 10


@pytest.mark.parametrize(
    ("sections", "kwargs", "message"),
    [
        ([], {}, "at least one section"),
        ([ListSection("A", rows(6, "a")), ListSection("B", rows(5, "b"))], {}, "at most 10 rows"),
        ([ListSection("A", [])], {}, "at least one row"),
        ([ListSection("A", rows(1, "a")), ListSection("", rows(1, "b"))], {}, "section title"),
        ([ListSection("x" * 25, rows(1))], {}, "section title"),
        ([ListSection("A", [ListRow("a", "x" * 25)])], {}, "row title"),
        ([ListSection("A", [ListRow("a", "A", "x" * 73)])], {}, "row description"),
        ([ListSection("A", [ListRow("x" * 201, "A")])], {}, "row id"),
        ([ListSection("A", [ListRow("a", "A"), ListRow("a", "B")])], {}, "unique"),
        ([ListSection("A", rows(1))], {"button": "x" * 21}, "list button"),
        ([ListSection("A", rows(1))], {"button": ""}, "list button"),
        ([ListSection("A", rows(1))], {"header": ImageHeader("https://x.test/a.png")}, "text"),
        ([ListSection("A", rows(1))], {"body": ""}, "body"),
        (["not a section"], {}, "ListSection"),
    ],
)
def test_list_message_limits(sections, kwargs, message):
    arguments = {"body": "Pick", "button": "Open", **kwargs}

    with pytest.raises(InvalidInteractiveContent, match=message):
        interactive.list_message(
            arguments.pop("body"), arguments.pop("button"), sections, **arguments
        )


# --- cta_url ------------------------------------------------------------------------------------


def test_cta_url_shape():
    content = interactive.cta_url(
        "Pay ₹1,450 for order SS-1001",
        "Pay now",
        "https://rzp.io/i/abc123",
        header=ImageHeader("https://cdn.test/logo.png"),
        footer="Link expires in 30 minutes",
    )

    assert content.interactive == {
        "type": "cta_url",
        "header": {"type": "image", "image": {"link": "https://cdn.test/logo.png"}},
        "body": {"text": "Pay ₹1,450 for order SS-1001"},
        "action": {
            "name": "cta_url",
            "parameters": {"display_text": "Pay now", "url": "https://rzp.io/i/abc123"},
        },
        "footer": {"text": "Link expires in 30 minutes"},
    }


@pytest.mark.parametrize(
    ("display_text", "url", "message"),
    [
        ("x" * 21, "https://rzp.io/i/a", "button text"),
        ("Pay", "javascript:alert(1)", "URL"),
        ("Pay", "rzp.io/i/a", "URL"),
        ("Pay", "", "URL"),
    ],
)
def test_cta_url_limits(display_text, url, message):
    with pytest.raises(InvalidInteractiveContent, match=message):
        interactive.cta_url("Pay", display_text, url)


# --- Catalog messages ---------------------------------------------------------------------------


def test_product_shape():
    content = interactive.product(
        "807010401234567", "KAJU-500", body="Fresh today", footer="GST incl."
    )

    assert content.summary == "Fresh today"
    assert content.interactive == {
        "type": "product",
        "body": {"text": "Fresh today"},
        "footer": {"text": "GST incl."},
        "action": {"catalog_id": "807010401234567", "product_retailer_id": "KAJU-500"},
    }


def test_product_without_body():
    content = interactive.product("807010401234567", "KAJU-500")

    assert "body" not in content.interactive
    assert content.summary == "Product KAJU-500"


@pytest.mark.parametrize(
    ("catalog_id", "retailer_id"), [("", "KAJU-500"), ("807", ""), ("807", "x" * 101)]
)
def test_product_needs_ids(catalog_id, retailer_id):
    with pytest.raises(InvalidInteractiveContent):
        interactive.product(catalog_id, retailer_id)


def test_product_list_shape():
    content = interactive.product_list(
        "807010401234567",
        "Diwali specials",
        "Handpicked for the festival",
        [
            ProductSection("Mithai", ["KAJU-500", "LADDU-250"]),
            ProductSection("Namkeen", ["BHUJIA"]),
        ],
        footer="Prices include GST",
    )

    assert content.summary == "Handpicked for the festival"
    assert content.interactive == {
        "type": "product_list",
        "header": {"type": "text", "text": "Diwali specials"},
        "body": {"text": "Handpicked for the festival"},
        "footer": {"text": "Prices include GST"},
        "action": {
            "catalog_id": "807010401234567",
            "sections": [
                {
                    "title": "Mithai",
                    "product_items": [
                        {"product_retailer_id": "KAJU-500"},
                        {"product_retailer_id": "LADDU-250"},
                    ],
                },
                {"title": "Namkeen", "product_items": [{"product_retailer_id": "BHUJIA"}]},
            ],
        },
    }


def test_product_list_allows_thirty_products_in_ten_sections():
    sections = [ProductSection(f"S{i}", [f"SKU-{i}-{j}" for j in range(3)]) for i in range(10)]

    content = interactive.product_list("807", "Header", "Body", sections)

    assert len(content.interactive["action"]["sections"]) == 10


@pytest.mark.parametrize(
    ("header", "sections", "message"),
    [
        ("Header", [], "at least one section"),
        ("Header", [ProductSection(f"S{i}", ["A"]) for i in range(11)], "at most 10 sections"),
        ("Header", [ProductSection("S", [f"A{i}" for i in range(31)])], "at most 30 products"),
        ("Header", [ProductSection("S", [])], "at least one product"),
        ("Header", [ProductSection("S", "SKU")], "at least one product"),
        ("Header", [ProductSection("", ["A"])], "section title"),
        ("", [ProductSection("S", ["A"])], "header"),
        ("x" * 61, [ProductSection("S", ["A"])], "header"),
    ],
)
def test_product_list_limits(header, sections, message):
    with pytest.raises(InvalidInteractiveContent, match=message):
        interactive.product_list("807", header, "Body", sections)


def test_catalog_message_shape():
    content = interactive.catalog_message(
        "Browse our full menu", thumbnail_retailer_id="KAJU-500", footer="Sharma Sweets"
    )

    assert content.interactive == {
        "type": "catalog_message",
        "body": {"text": "Browse our full menu"},
        "footer": {"text": "Sharma Sweets"},
        "action": {
            "name": "catalog_message",
            "parameters": {"thumbnail_product_retailer_id": "KAJU-500"},
        },
    }
    plain = interactive.catalog_message("Browse")
    assert plain.interactive["action"] == {"name": "catalog_message"}


# --- address_message ----------------------------------------------------------------------------


def test_address_message_shape():
    content = interactive.address_message("Where should we deliver order SS-1001?")

    assert content.summary == "Where should we deliver order SS-1001?"
    assert content.interactive == {
        "type": "address_message",
        "body": {"text": "Where should we deliver order SS-1001?"},
        "action": {"name": "address_message", "parameters": {"country": "IN"}},
    }


def test_address_message_with_values_and_validation_errors():
    content = interactive.address_message(
        "Please check your pincode",
        values={"name": "Priya Sharma", "in_pin_code": "41100"},
        validation_errors={"in_pin_code": "We don't deliver to this pincode."},
    )

    assert content.interactive["action"]["parameters"] == {
        "country": "IN",
        "values": {"name": "Priya Sharma", "in_pin_code": "41100"},
        "validation_errors": {"in_pin_code": "We don't deliver to this pincode."},
    }


@pytest.mark.parametrize(
    "kwargs",
    [{"values": {"name": 5}}, {"values": ["name"]}, {"validation_errors": {"": "x"}}],
)
def test_address_message_rejects_bad_maps(kwargs):
    with pytest.raises(InvalidInteractiveContent):
        interactive.address_message("Address?", **kwargs)


def test_address_message_needs_a_body():
    with pytest.raises(InvalidInteractiveContent, match="body"):
        interactive.address_message("")
