"""Offers services (docs/contracts/services-and-offers.md): the import surface for other apps."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class AppliedOffer:
    claim_id: uuid.UUID
    code: str
    discount_paise: int


def match_code(workspace_id, text: str | None):
    """The active offer code that ``text`` is exactly, or None."""
    return None


def apply_to_checkout(order) -> AppliedOffer | None:
    """Apply the contact's open claim to ``order``; None when no offer applies."""
    return None


def release_for_order(order) -> None:
    """Put the claim applied to ``order`` back to claimed."""
