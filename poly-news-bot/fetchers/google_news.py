"""Google News RSS fetcher for Polymarket queries."""
from __future__ import annotations

import logging

import aiohttp

from ._rss_helpers import fetch_feed_items
from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search?q=polymarket&hl=en-US&gl=US&ceid=US:en"
)


class GoogleNewsFetcher(BaseFetcher):
    name = "google_news"
    source_label = "Google News"

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        try:
            items = await fetch_feed_items(
                session,
                GOOGLE_NEWS_URL,
                source=self.name,
                source_label=self.source_label,
            )
            log.info("[%s] fetched %d items", self.name, len(items))
            return items
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []