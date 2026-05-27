"""Hacker News (Algolia) search fetcher."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from utils.hashing import news_hash
from utils.http import fetch_json

from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

HN_URL = (
    "https://hn.algolia.com/api/v1/search_by_date?query=polymarket&tags=story"
)


class HackerNewsFetcher(BaseFetcher):
    name = "hacker_news"
    source_label = "Hacker News"

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        try:
            data = await fetch_json(session, HN_URL)
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []

        items: list[NewsItem] = []
        for hit in data.get("hits", []) if isinstance(data, dict) else []:
            url = hit.get("url") or (
                f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                if hit.get("objectID")
                else None
            )
            title = hit.get("title") or hit.get("story_title") or ""
            if not url or not title:
                continue
            ts = hit.get("created_at_i")
            try:
                published_at = (
                    datetime.fromtimestamp(int(ts), tz=timezone.utc)
                    if ts
                    else datetime.now(timezone.utc)
                )
            except Exception:  # noqa: BLE001
                published_at = datetime.now(timezone.utc)
            items.append(
                NewsItem(
                    id_hash=news_hash(url),
                    title=title[:300],
                    url=url,
                    source=self.name,
                    source_label=self.source_label,
                    published_at=published_at,
                    summary=None,
                    author=hit.get("author"),
                )
            )
        log.info("[%s] fetched %d items", self.name, len(items))
        return items