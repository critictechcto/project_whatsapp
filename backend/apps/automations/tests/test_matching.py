import pytest

from apps.automations.matching import keyword_matches, normalize, normalize_keywords


def test_normalize_collapses_whitespace_and_casefolds():
    assert normalize("  PRICE \n  List ") == "price list"
    assert normalize("STRASSE") == normalize("straße")
    assert normalize(None) == ""


def test_normalize_keywords_drops_blanks_and_duplicates():
    assert normalize_keywords(["Price", " PRICE ", "", "  ", "rate card"]) == ["price", "rate card"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PRICE", True),
        ("  price  ", True),
        ("Price?", True),
        ("price!!", True),
        ("rate  CARD", True),
        ("price list", False),
        ("what is the price", False),
        ("prices", False),
        ("", False),
    ],
)
def test_exact(text, expected):
    assert keyword_matches(text, ["price", "rate card"], "exact") is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What is the PRICE?", True),
        ("price", True),
        ("price.", True),
        ("send the rate   card please", True),
        ("priceless", False),
        ("overpriced", False),
        ("rate cards", False),
        ("", False),
    ],
)
def test_contains_matches_whole_words(text, expected):
    assert keyword_matches(text, ["price", "rate card"], "contains") is expected


def test_contains_works_for_hindi():
    assert keyword_matches("इसकी कीमत क्या है?", ["कीमत"], "contains")


def test_unknown_mode_never_matches():
    assert not keyword_matches("price", ["price"], "regex")
