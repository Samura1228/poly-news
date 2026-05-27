"""Bing News RSS fetcher for Polymarket queries."""
from __future__ import annotations

import logging

import aiohttp

from ._rss_helpers import fetch_feed_items
from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

BING_NEWS_URL = "https://www.bing.com/news/search?q=polymarket&format=rss"


class BingNewsFetcher(BaseFetcher):
    name = "bing_news"
    source_label = "Bing News"

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        try:
            items = await fetch_feed_items(
                session,
                BING_NEWS_URL,
                source=self.name,
                source_label=self.source_label,
            )
            log.info("[%s] fetched %d items", self.name, len(items))
            return items
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []