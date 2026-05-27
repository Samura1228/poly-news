"""Substack fetcher (best-effort placeholder).

Substack has no global keyword RSS. To enable, list specific newsletter feeds
in `SUBSTACK_FEEDS` below (one URL per line in a future env var). Until then
this returns []. Implemented to satisfy the architecture inventory.
"""
from __future__ import annotations

import logging

import aiohttp

from utils.keyword_filter import matches_polymarket

from ._rss_helpers import fetch_feed_items
from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

# Curated Substack newsletter feeds known to cover prediction markets / crypto.
# Edit this list to add more. Empty by default → fetcher returns [].
SUBSTACK_FEEDS: list[tuple[str, str]] = [
    # ("source_label", "https://example.substack.com/feed"),
]


class SubstackFetcher(BaseFetcher):
    name = "substack"
    source_label = "Substack"

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        if not SUBSTACK_FEEDS:
            log.debug("[%s] no curated feeds configured; skipping", self.name)
            return []
        merged: dict[str, NewsItem] = {}
        for label, url in SUBSTACK_FEEDS:
            try:
                raw = await fetch_feed_items(
                    session, url, source=self.name, source_label=label
                )
                for it in raw:
                    if matches_polymarket(f"{it.title}\n{it.summary or ''}"):
                        merged.setdefault(it.id_hash, it)
            except Exception as e:  # noqa: BLE001
                log.debug("[%s] feed %s error: %s", self.name, url, e)
        items = list(merged.values())
        log.info("[%s] fetched %d items", self.name, len(items))
        return items