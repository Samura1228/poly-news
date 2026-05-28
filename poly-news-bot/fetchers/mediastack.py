"""Mediastack fetcher (optional, requires free API key).

Free tier: 100 requests/month — very low; treat as a secondary source.
Sign up: https://mediastack.com/signup/free

Endpoint:
  https://api.mediastack.com/v1/news?access_key={key}&keywords=polymarket
    &languages=en&sort=published_desc
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp
from dateutil import parser as date_parser

from utils.hashing import news_hash
from utils.http import fetch_json

from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)


class MediastackFetcher(BaseFetcher):
    name = "mediastack"
    source_label = "Mediastack"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        url = (
            "https://api.mediastack.com/v1/news"
            f"?access_key={self.api_key}"
            "&keywords=polymarket&languages=en&sort=published_desc"
        )
        try:
            data = await fetch_json(session, url)
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []

        if not isinstance(data, dict):
            return []

        # Mediastack returns errors as {"error": {...}} rather than `data`.
        if "error" in data and not data.get("data"):
            err = data.get("error")
            log.warning("[%s] API error: %s", self.name, err)
            return []

        results = data.get("data") or []
        if not isinstance(results, list):
            return []

        items: list[NewsItem] = []
        for post in results:
            if not isinstance(post, dict):
                continue
            title = (post.get("title") or "").strip()
            link = (post.get("url") or "").strip()
            if not title or not link:
                continue

            published_raw = post.get("published_at")
            try:
                published_at = (
                    date_parser.parse(published_raw)
                    if published_raw
                    else datetime.now(timezone.utc)
                )
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                published_at = datetime.now(timezone.utc)

            summary_raw = post.get("description") or ""
            summary = (summary_raw[:500] if isinstance(summary_raw, str) else None) or None

            author_raw = post.get("author")
            author = author_raw.strip() if isinstance(author_raw, str) and author_raw.strip() else None

            image_url = None
            try:
                raw_img = post.get("image")
                if isinstance(raw_img, str) and raw_img.startswith("http"):
                    image_url = raw_img
            except Exception:  # noqa: BLE001
                image_url = None

            items.append(
                NewsItem(
                    id_hash=news_hash(link),
                    title=title[:300],
                    url=link,
                    source=self.name,
                    source_label=self.source_label,
                    published_at=published_at.astimezone(timezone.utc),
                    summary=summary,
                    author=author,
                    image_url=image_url,
                )
            )

        log.info("[%s] fetched %d items", self.name, len(items))
        return items