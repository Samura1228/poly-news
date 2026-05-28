"""Polymarket official blog fetcher (RSS with HTML scrape fallback)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from utils.hashing import news_hash
from utils.http import fetch_bytes, fetch_text

from ._rss_helpers import fetch_feed_items
from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

RSS_CANDIDATES = [
    "https://polymarket.com/blog/rss.xml",
    "https://polymarket.com/learn/rss.xml",
    "https://polymarket.com/blog/feed",
    "https://polymarket.com/blog/rss",
]

BLOG_HTML_URL = "https://polymarket.com/blog"


class PolymarketBlogFetcher(BaseFetcher):
    name = "polymarket_blog"
    source_label = "Polymarket Blog"

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        # 1) Try each RSS candidate.
        for url in RSS_CANDIDATES:
            try:
                items = await fetch_feed_items(
                    session, url, source=self.name, source_label=self.source_label
                )
                if items:
                    log.info("[%s] fetched %d items from %s", self.name, len(items), url)
                    return items
            except Exception as e:  # noqa: BLE001
                log.debug("[%s] feed candidate failed %s: %s", self.name, url, e)

        # 2) Fallback: HTML scrape.
        try:
            html = await fetch_text(session, BLOG_HTML_URL)
            items = await asyncio.to_thread(self._scrape_html, html)
            log.info(
                "[%s] fetched %d items via HTML scrape fallback",
                self.name,
                len(items),
            )
            return items
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []

    def _scrape_html(self, html: str) -> list[NewsItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[NewsItem] = []
        seen: set[str] = set()
        # Be flexible: look at all <a> tags whose href points to a blog post-ish path.
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href:
                continue
            # Only follow blog-ish paths.
            if "/blog/" not in href and not href.startswith("/blog"):
                continue
            full = urljoin(BLOG_HTML_URL, href)
            if full in seen:
                continue
            seen.add(full)
            text = (a.get_text() or "").strip()
            if not text or len(text) < 8:
                continue
            image_url = None
            try:
                img_tag = a.find("img")
                if img_tag is not None:
                    src = img_tag.get("src") or img_tag.get("data-src")
                    if isinstance(src, str) and src.startswith("http"):
                        image_url = src
            except Exception:  # noqa: BLE001
                image_url = None
            items.append(
                NewsItem(
                    id_hash=news_hash(full),
                    title=text[:300],
                    url=full,
                    source=self.name,
                    source_label=self.source_label,
                    published_at=datetime.now(timezone.utc),
                    summary=None,
                    author=None,
                    image_url=image_url,
                )
            )
        return items