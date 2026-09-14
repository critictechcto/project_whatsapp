"""Pure keyword normalisation and matching for the ``keyword`` trigger."""

import re
import string
from collections.abc import Iterable

from .schema_enums import KEYWORD_MATCHES

EXACT, CONTAINS = KEYWORD_MATCHES
# Stripped from both ends of a message for exact matching, so "Price?" matches "price".
EDGE_PUNCTUATION = string.punctuation + "".join(
    map(chr, (0x0964, 0x0965, 0xBF, 0xA1, 0x2026, 0x201C, 0x201D, 0x2018, 0x2019))
)  # danda, double danda, inverted ? and !, ellipsis, curly quotes


def normalize(text: str | None) -> str:
    """Collapse whitespace and casefold (``"  PRICE  list "`` → ``"price list"``)."""
    return " ".join(str(text or "").split()).casefold()


def normalize_keywords(keywords: Iterable[str]) -> list[str]:
    """Normalised, non-empty, de-duplicated keywords in their original order."""
    seen: dict[str, None] = {}
    for keyword in keywords:
        normalized = normalize(keyword)
        if normalized:
            seen.setdefault(normalized, None)
    return list(seen)


def keyword_matches(text: str | None, keywords: Iterable[str], mode: str) -> bool:
    """``exact``: the whole message (ignoring surrounding punctuation) equals a keyword.
    ``contains``: a keyword appears as whole words, e.g. "price" matches "the price?" but not
    "priceless"."""
    message = normalize(text)
    if not message:
        return False
    keywords = normalize_keywords(keywords)
    if mode == EXACT:
        candidates = {message, message.strip(EDGE_PUNCTUATION).strip()}
        return any(keyword in candidates for keyword in keywords)
    if mode == CONTAINS:
        return any(
            re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", message) is not None
            for keyword in keywords
        )
    return False
