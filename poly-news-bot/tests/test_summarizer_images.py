"""Tests for the per-cycle image deduplication in :mod:`summarizer`.

Locks in the fix for the bug where the same underlying image (differing only
by query-string size params, tracking params, or host casing) was being
attached to multiple digests in the same cycle.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fetchers.base import NewsItem
from summarizer import (
    Digest,
    _assign_unique_images,
    _normalize_image_url,
    _unique_image_urls,
)


def _make_item(idx: int, image_url: str | None) -> NewsItem:
    return NewsItem(
        id_hash=f"hash-{idx}",
        title=f"Title {idx}",
        url=f"https://example.test/{idx}",
        source="test",
        source_label="Test",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        summary=f"Summary {idx}",
        author=None,
        image_url=image_url,
    )


def test_normalize_strips_query_fragment_and_lowercases_host():
    assert (
        _normalize_image_url("https://CDN.A.COM/foo.jpg?w=800")
        == "https://cdn.a.com/foo.jpg"
    )
    assert (
        _normalize_image_url("https://b.com/bar.png?utm_source=x#frag")
        == "https://b.com/bar.png"
    )
    assert (
        _normalize_image_url("https://cdn.a.com/foo.jpg?w=400")
        == _normalize_image_url("https://CDN.A.COM/foo.jpg?w=800")
    )


def test_unique_image_urls_dedupes_by_normalized_form():
    items = [
        _make_item(0, "https://cdn.a.com/foo.jpg?w=400"),
        _make_item(1, "https://CDN.A.COM/foo.jpg?w=800"),
        _make_item(2, "https://b.com/bar.png"),
        _make_item(3, "https://b.com/bar.png?utm=x"),
        _make_item(4, None),
    ]
    unique = _unique_image_urls(items)
    # Only 2 truly distinct images.
    assert len(unique) == 2
    # First-seen original URL is preserved.
    assert unique[0][1] == "https://cdn.a.com/foo.jpg?w=400"
    assert unique[1][1] == "https://b.com/bar.png"


def test_assign_unique_images_to_three_digests():
    items = [
        _make_item(0, "https://cdn.a.com/foo.jpg?w=400"),
        _make_item(1, "https://CDN.A.COM/foo.jpg?w=800"),
        _make_item(2, "https://b.com/bar.png"),
        _make_item(3, "https://b.com/bar.png?utm=x"),
        _make_item(4, None),
    ]
    digests = [Digest(text=f"d{i}") for i in range(3)]
    _assign_unique_images(digests, items)

    cdn_a_urls = {
        "https://cdn.a.com/foo.jpg?w=400",
        "https://CDN.A.COM/foo.jpg?w=800",
    }
    assert digests[0].image_url in cdn_a_urls
    assert digests[1].image_url == "https://b.com/bar.png"
    assert digests[2].image_url is None  # no third unique image

    non_none = {d.image_url for d in digests if d.image_url}
    assert len(non_none) == 2


def test_assign_unique_images_assertion_holds_with_no_images():
    items = [_make_item(0, None), _make_item(1, None)]
    digests = [Digest(text="a"), Digest(text="b")]
    _assign_unique_images(digests, items)
    assert all(d.image_url is None for d in digests)


def test_assign_unique_images_more_images_than_digests():
    items = [
        _make_item(0, "https://a.com/1.jpg"),
        _make_item(1, "https://a.com/2.jpg"),
        _make_item(2, "https://a.com/3.jpg"),
    ]
    digests = [Digest(text="only-one")]
    _assign_unique_images(digests, items)
    assert digests[0].image_url == "https://a.com/1.jpg"