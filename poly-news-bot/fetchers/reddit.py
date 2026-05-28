"""Reddit fetcher: r/polymarket and cross-subreddit search."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from utils.hashing import news_hash
from utils.http import fetch_json

from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

REDDIT_UA = "PolyNewsBot/1.0 (by polymarket-news-bot)"

ENDPOINTS = [
    "https://www.reddit.com/r/polymarket/new.json?limit=50",
    "https://www.reddit.com/search.json?q=polymarket&sort=new&limit=50",
]


class RedditFetcher(BaseFetcher):
    name = "reddit"
    source_label = "Reddit"

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        headers = {"User-Agent": REDDIT_UA}
        merged: dict[str, NewsItem] = {}
        for url in ENDPOINTS:
            try:
                data = await fetch_json(session, url, headers=headers)
                items = self._parse(data)
                for it in items:
                    merged[it.id_hash] = it
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] error fetching %s: %s", self.name, url, e)

        items = list(merged.values())
        log.info("[%s] fetched %d items", self.name, len(items))
        return items

    def _parse(self, data: Any) -> list[NewsItem]:
        items: list[NewsItem] = []
        if not isinstance(data, dict):
            return items
        children = data.get("data", {}).get("children") or []
        for child in children:
            post = child.get("data") or {}
            permalink = post.get("permalink")
            url = (
                f"https://www.reddit.com{permalink}"
                if permalink
                else post.get("url")
            )
            title = post.get("title") or ""
            if not url or not title:
                continue
            created = post.get("created_utc")
            try:
                published_at = (
                    datetime.fromtimestamp(float(created), tz=timezone.utc)
                    if created
                    else datetime.now(timezone.utc)
                )
            except Exception:  # noqa: BLE001
                published_at = datetime.now(timezone.utc)
            subreddit = post.get("subreddit") or ""
            label = (
                f"r/{subreddit}" if subreddit else self.source_label
            )
            image_url = None
            try:
                preview = post.get("preview") or {}
                images = preview.get("images") or []
                if images and isinstance(images, list):
                    src = (images[0] or {}).get("source") or {}
                    raw = src.get("url")
                    if isinstance(raw, str) and raw.startswith("http"):
                        # Reddit HTML-encodes ampersands.
                        image_url = raw.replace("&amp;", "&")
                if not image_url:
                    thumb = post.get("thumbnail")
                    if isinstance(thumb, str) and thumb.startswith("http"):
                        image_url = thumb
            except Exception:  # noqa: BLE001
                image_url = None
            items.append(
                NewsItem(
                    id_hash=news_hash(url),
                    title=title[:300],
                    url=url,
                    source=self.name,
                    source_label=label,
                    published_at=published_at,
                    summary=(post.get("selftext") or None) or None,
                    author=post.get("author"),
                    image_url=image_url,
                )
            )
        return items