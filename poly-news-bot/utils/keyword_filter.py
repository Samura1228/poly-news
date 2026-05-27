"""Polymarket keyword filtering."""
from __future__ import annotations

import re

# Case-insensitive matchers. We use simple substring matching per architecture
# doc (§1 / keyword filter rules) so things like "Polymarket's" still match.
# Word boundary is used on the LEFT side only to avoid matching things like
# "abcpolymarket" while still matching "polymarket's", "polymarket-based", etc.
_PATTERNS = [
    re.compile(r"\bpolymarket", re.IGNORECASE),
    re.compile(r"\bpoly\s+market\b", re.IGNORECASE),
]


def matches_polymarket(text: str | None) -> bool:
    """Return True if `text` mentions Polymarket (or 'poly market')."""
    if not text:
        return False
    for pat in _PATTERNS:
        if pat.search(text):
            return True
    return False