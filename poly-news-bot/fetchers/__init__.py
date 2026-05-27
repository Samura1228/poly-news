"""Fetcher registry — instantiates all enabled fetchers from settings."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import BaseFetcher, NewsItem
from .bing_news import BingNewsFetcher
from .cryptopanic import CryptoPanicFetcher
from .github import GitHubFetcher
from .google_news import GoogleNewsFetcher
from .hacker_news import HackerNewsFetcher
from .mediastack import MediastackFetcher
from .messari import MessariFetcher
from .newsdata import NewsDataFetcher
from .nitter import NitterFetcher
from .polymarket_blog import PolymarketBlogFetcher
from .reddit import RedditFetcher
from .rss_generic import build_generic_fetchers
from .substack import SubstackFetcher
from .twitter_api import TwitterApiFetcher
from .youtube import YouTubeFetcher

if TYPE_CHECKING:
    from config import Settings

log = logging.getLogger(__name__)


def get_enabled_fetchers(settings: "Settings") -> list[BaseFetcher]:
    """Build the list of enabled fetchers, skipping disabled or unconfigured ones."""
    disabled = {s.strip().lower() for s in settings.disabled_sources}

    candidates: list[BaseFetcher] = []

    # Always-on (no API key needed).
    candidates.append(GoogleNewsFetcher())
    candidates.append(BingNewsFetcher())
    candidates.append(PolymarketBlogFetcher())
    candidates.append(NitterFetcher(mirrors=settings.nitter_mirrors))
    candidates.append(RedditFetcher())
    candidates.append(HackerNewsFetcher())
    candidates.append(YouTubeFetcher(channel_id=settings.polymarket_youtube_channel_id))
    candidates.append(GitHubFetcher(token=settings.github_token))
    candidates.append(MessariFetcher())
    candidates.append(SubstackFetcher())

    # Generic keyword-filtered crypto RSS feeds (multiple instances).
    candidates.extend(build_generic_fetchers(disabled))

    # Optional, gated on credentials.
    if settings.cryptopanic_api_key:
        candidates.append(
            CryptoPanicFetcher(
                api_key=settings.cryptopanic_api_key,
                api_plan=settings.cryptopanic_api_plan,
            )
        )
    else:
        log.info("CryptoPanic disabled (no CRYPTOPANIC_API_KEY).")

    if settings.newsdata_api_key:
        candidates.append(NewsDataFetcher(api_key=settings.newsdata_api_key))
    else:
        log.info("NewsData.io disabled (no NEWSDATA_API_KEY).")

    if settings.mediastack_api_key:
        candidates.append(MediastackFetcher(api_key=settings.mediastack_api_key))
    else:
        log.info("Mediastack disabled (no MEDIASTACK_API_KEY).")

    if settings.twitter_bearer_token:
        candidates.append(TwitterApiFetcher(bearer_token=settings.twitter_bearer_token))
    else:
        log.info("Twitter API disabled (no TWITTER_BEARER_TOKEN).")

    # Filter explicitly-disabled by slug.
    enabled: list[BaseFetcher] = []
    for f in candidates:
        if f.name.lower() in disabled:
            log.info("Source %s disabled via DISABLED_SOURCES.", f.name)
            continue
        enabled.append(f)

    log.info(
        "Enabled %d fetchers: %s",
        len(enabled),
        ", ".join(f.name for f in enabled),
    )
    return enabled


__all__ = ["get_enabled_fetchers", "BaseFetcher", "NewsItem"]