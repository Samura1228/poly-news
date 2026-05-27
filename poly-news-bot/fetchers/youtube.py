"""YouTube fetcher: Polymarket channel feed + search feed (best-effort)."""
from __future__ import annotations

import logging

import aiohttp

from utils.keyword_filter import matches_polymarket

from ._rss_helpers import fetch_feed_items
from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

CHANNEL_FEED_TMPL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
# Note: this endpoint is unofficial / fragile. If it 404s the fetcher just
# returns the channel results (or [] if neither works).
SEARCH_FEED = "https://www.youtube.com/feeds/videos.xml?search_query=polymarket"


class YouTubeFetcher(BaseFetcher):
    name = "youtube"
    source_label = "YouTube"

    def __init__(self, channel_id: str = "") -> None:
        self.channel_id = (channel_id or "").strip()

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        merged: dict[str, NewsItem] = {}

        # Channel feed (if configured).
        if self.channel_id:
            url = CHANNEL_FEED_TMPL.format(cid=self.channel_id)
            try:
                items = await fetch_feed_items(
                    session,
                    url,
                    source=self.name,
                    source_label="YouTube — Polymarket",
                )
                for it in items:
                    merged[it.id_hash] = it
            except Exception as e:  # noqa: BLE001
                log.debug("[%s] channel feed error: %s", self.name, e)

        # Search feed (filter by keyword as belt-and-braces).
        try:
            items = await fetch_feed_items(
                session,
                SEARCH_FEED,
                source=self.name,
                source_label="YouTube (search)",
            )
            for it in items:
                if matches_polymarket(f"{it.title}\n{it.summary or ''}"):
                    merged.setdefault(it.id_hash, it)
        except Exception as e:  # noqa: BLE001
            log.debug("[%s] search feed error: %s", self.name, e)

        items = list(merged.values())
        log.info("[%s] fetched %d items", self.name, len(items))
        return items