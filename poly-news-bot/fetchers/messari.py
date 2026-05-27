"""Messari news fetcher (keyword-filtered RSS)."""
from __future__ import annotations

import logging

import aiohttp

from utils.keyword_filter import matches_polymarket

from ._rss_helpers import fetch_feed_items
from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

# Messari publishes a news RSS at this path (subject to change).
MESSARI_RSS = "https://messari.io/rss"


class MessariFetcher(BaseFetcher):
    name = "messari"
    source_label = "Messari"

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        try:
            raw = await fetch_feed_items(
                session, MESSARI_RSS, source=self.name, source_label=self.source_label
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []
        filtered = [
            it for it in raw if matches_polymarket(f"{it.title}\n{it.summary or ''}")
        ]
        log.info(
            "[%s] fetched %d items (%d after keyword filter)",
            self.name,
            len(raw),
            len(filtered),
        )
        return filtered