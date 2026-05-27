"""NewsData.io fetcher (optional, requires free API key).

Free tier: 200 requests/day — plenty for a 30-min poll cycle (~48/day).
Sign up: https://newsdata.io/register

Endpoint: https://newsdata.io/api/1/latest?apikey={key}&q=polymarket&language=en

Recommended free replacement for CryptoPanic after its Developer free tier
ended on 2026-04-01.
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


class NewsDataFetcher(BaseFetcher):
    name = "newsdata"
    source_label = "NewsData.io"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        url = (
            "https://newsdata.io/api/1/latest"
            f"?apikey={self.api_key}&q=polymarket&language=en"
        )
        try:
            data = await fetch_json(session, url)
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []

        if not isinstance(data, dict):
            return []

        status = data.get("status")
        if status and str(status).lower() != "success":
            log.warning(
                "[%s] API returned non-success status=%s message=%s",
                self.name,
                status,
                data.get("message") or data.get("results"),
            )
            return []

        results = data.get("results") or []
        if not isinstance(results, list):
            return []

        items: list[NewsItem] = []
        for post in results:
            if not isinstance(post, dict):
                continue
            title = (post.get("title") or "").strip()
            link = (post.get("link") or "").strip()
            if not title or not link:
                continue

            published_raw = post.get("pubDate") or post.get("pubDate_TZ")
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

            author = None
            creator = post.get("creator")
            if isinstance(creator, list) and creator:
                first = creator[0]
                if isinstance(first, str) and first.strip():
                    author = first.strip()
            elif isinstance(creator, str) and creator.strip():
                author = creator.strip()

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
                )
            )

        log.info("[%s] fetched %d items", self.name, len(items))
        return items