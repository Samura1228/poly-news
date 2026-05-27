"""Unit tests for utils.hashing.canonicalize_url and news_hash."""
from __future__ import annotations

from utils.hashing import canonicalize_url, news_hash


def test_lowercase_scheme_and_host() -> None:
    assert (
        canonicalize_url("HTTPS://Example.COM/Foo")
        == "https://example.com/Foo"
    )


def test_strip_fragment() -> None:
    assert (
        canonicalize_url("https://example.com/post#section")
        == "https://example.com/post"
    )


def test_strip_trailing_slash() -> None:
    assert (
        canonicalize_url("https://example.com/foo/")
        == "https://example.com/foo"
    )
    # Root path stays as-is.
    assert canonicalize_url("https://example.com/") in (
        "https://example.com/",
        "https://example.com",
    )


def test_strip_utm_params() -> None:
    url = (
        "https://example.com/a?utm_source=twitter&utm_medium=social"
        "&utm_campaign=x&id=42"
    )
    assert canonicalize_url(url) == "https://example.com/a?id=42"


def test_strip_other_tracking_params() -> None:
    url = "https://example.com/a?fbclid=abc&gclid=def&ref=zzz&id=1"
    assert canonicalize_url(url) == "https://example.com/a?id=1"


def test_sort_query_params() -> None:
    url = "https://example.com/a?b=2&a=1"
    assert canonicalize_url(url) == "https://example.com/a?a=1&b=2"


def test_google_news_redirect_resolves() -> None:
    inner = "https://realsite.com/article-123"
    url = f"https://news.google.com/articles/xyz?url={inner}&hl=en"
    canon = canonicalize_url(url)
    assert canon == "https://realsite.com/article-123"


def test_google_news_no_url_param_kept_as_is_hash_stable() -> None:
    # If no `url=` param, we should still produce a stable canonical form
    # from the google news URL itself.
    url = "https://news.google.com/articles/abc?hl=en"
    canon = canonicalize_url(url)
    assert canon.startswith("https://news.google.com/")
    # Idempotent
    assert canonicalize_url(canon) == canon


def test_news_hash_stable_across_equivalent_urls() -> None:
    a = "HTTPS://Example.com/foo/?utm_source=x&id=1#frag"
    b = "https://example.com/foo?id=1"
    assert news_hash(a) == news_hash(b)


def test_news_hash_changes_for_different_paths() -> None:
    assert news_hash("https://example.com/a") != news_hash("https://example.com/b")


def test_news_hash_is_sha256_hex() -> None:
    h = news_hash("https://example.com/a")
    assert len(h) == 64
    int(h, 16)  # parses as hex