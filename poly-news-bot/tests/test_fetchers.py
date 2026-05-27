"""Smoke tests for the fetcher registry."""
from __future__ import annotations

from config import Settings
from fetchers import get_enabled_fetchers
from fetchers.base import BaseFetcher


def _make_settings(**overrides) -> Settings:
    defaults = dict(
        telegram_bot_token="123:fake",
        poll_interval_minutes=30,
        startup_delay_seconds=30,
        backfill_window_hours=24,
        max_items_per_cycle=10,
        database_path="./data/bot.db",
        news_retention_days=30,
        http_timeout_seconds=20,
        http_user_agent="PolyNewsBot-Test/1.0",
        cryptopanic_api_key="",
        twitter_bearer_token="",
        github_token="",
        disabled_sources=[],
        nitter_mirrors=["nitter.net"],
        polymarket_youtube_channel_id="",
        log_level="INFO",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_registry_returns_non_empty_list_with_token() -> None:
    fetchers = get_enabled_fetchers(_make_settings())
    assert len(fetchers) > 0
    for f in fetchers:
        assert isinstance(f, BaseFetcher)
        assert isinstance(f.name, str) and f.name
        assert isinstance(f.source_label, str) and f.source_label


def test_optional_sources_gated_on_credentials() -> None:
    fetchers = get_enabled_fetchers(_make_settings())
    names = {f.name for f in fetchers}
    # Without keys, these must NOT be present:
    assert "cryptopanic" not in names
    assert "twitter_api" not in names

    fetchers2 = get_enabled_fetchers(
        _make_settings(cryptopanic_api_key="abc", twitter_bearer_token="xyz")
    )
    names2 = {f.name for f in fetchers2}
    assert "cryptopanic" in names2
    assert "twitter_api" in names2


def test_disabled_sources_are_skipped() -> None:
    fetchers = get_enabled_fetchers(_make_settings(disabled_sources=["google_news"]))
    names = {f.name for f in fetchers}
    assert "google_news" not in names
    # But other always-on sources should still be present.
    assert "bing_news" in names


def test_every_fetcher_module_imports() -> None:
    # Importing the package already imports every fetcher; this is a
    # belt-and-braces explicit check.
    import importlib

    for module in [
        "fetchers.google_news",
        "fetchers.bing_news",
        "fetchers.polymarket_blog",
        "fetchers.nitter",
        "fetchers.twitter_api",
        "fetchers.reddit",
        "fetchers.hacker_news",
        "fetchers.cryptopanic",
        "fetchers.rss_generic",
        "fetchers.messari",
        "fetchers.youtube",
        "fetchers.github",
        "fetchers.substack",
    ]:
        importlib.import_module(module)