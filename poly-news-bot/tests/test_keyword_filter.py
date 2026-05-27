"""Unit tests for utils.keyword_filter.matches_polymarket."""
from __future__ import annotations

from utils.keyword_filter import matches_polymarket


def test_basic_match() -> None:
    assert matches_polymarket("Polymarket hits new ATH")


def test_case_insensitive() -> None:
    assert matches_polymarket("polymarket hits new ATH")
    assert matches_polymarket("POLYMARKET hits new ATH")


def test_no_match_empty() -> None:
    assert not matches_polymarket("")
    assert not matches_polymarket(None)


def test_no_match_unrelated() -> None:
    assert not matches_polymarket("Bitcoin hits new high")
    assert not matches_polymarket("Just a regular news article about Ethereum.")


def test_match_with_punctuation() -> None:
    assert matches_polymarket("'Polymarket's' new feature is exciting.")
    assert matches_polymarket("Polymarket-based predictions are booming")
    assert matches_polymarket("via Polymarket.")


def test_poly_market_variant() -> None:
    assert matches_polymarket("the poly market sector is growing")


def test_word_boundary_prevents_left_substring() -> None:
    # Per architecture doc we use substring with a left word-boundary; a token
    # like "xyzpolymarket" embedded into another word should NOT match.
    assert not matches_polymarket("xyzpolymarket")
    # But trailing characters are fine ("polymarketing" technically contains
    # "polymarket" — keep simple, accept it).
    assert matches_polymarket("polymarketing")


def test_match_inside_paragraph() -> None:
    text = (
        "The crypto landscape is changing fast. Today, Polymarket announced "
        "a new partnership with X. Many traders are excited."
    )
    assert matches_polymarket(text)