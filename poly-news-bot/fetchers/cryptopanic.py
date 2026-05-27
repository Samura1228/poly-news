"""CryptoPanic news fetcher (optional, requires PAID API key as of 2026-04-01).

The free Developer API tier was discontinued on April 1, 2026. The v1 endpoint
(`/api/v1/posts/`) is gone; v2 requires a paid plan and the URL embeds the plan
slug: `/api/<plan>/v2/posts/` where `<plan>` is one of: developer, growth,
enterprise.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp
from dateutil import parser as date_parser

from utils.hashing import news_hash
from utils.http import fetch_json
from utils.keyword_filter import matches_polymarket

from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

_VALID_PLANS = {"developer", "growth", "enterprise"}


class CryptoPanicFetcher(BaseFetcher):
    name = "cryptopanic"
    source_label = "CryptoPanic"

    def __init__(self, api_key: str, api_plan: str = "developer") -> None:
        self.api_key = api_key
        plan = (api_plan or "developer").strip().lower()
        if plan not in _VALID_PLANS:
            log.warning(
                "CryptoPanic: unknown CRYPTOPANIC_API_PLAN=%r — falling back to 'developer'. "
                "Valid values: %s",
                api_plan,
                ", ".join(sorted(_VALID_PLANS)),
            )
            plan = "developer"
        self.api_plan = plan
        log.warning(
            "CryptoPanic Developer free tier ended 2026-04-01. "
            "Ensure your CRYPTOPANIC_API_PLAN (=%s) matches your paid subscription.",
            self.api_plan,
        )

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        url = (
            f"https://cryptopanic.com/api/{self.api_plan}/v2/posts/"
            f"?auth_token={self.api_key}&public=true"
        )
        try:
            data = await fetch_json(session, url)
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []

        items: list[NewsItem] = []
        results = data.get("results", []) if isinstance(data, dict) else []
        for post in results:
            if not isinstance(post, dict):
                continue
            title = post.get("title") or ""
            link = post.get("url") or ""
            if not link or not title:
                continue

            # Collect currency codes if present for keyword matching.
            currencies = post.get("currencies") or []
            currency_codes = []
            if isinstance(currencies, list):
                for c in currencies:
                    if isinstance(c, dict):
                        code = c.get("code") or c.get("title") or ""
                        if code:
                            currency_codes.append(str(code))

            combined = " ".join(
                [
                    title,
                    str(post.get("slug") or ""),
                    " ".join(currency_codes),
                ]
            )
            if not matches_polymarket(combined):
                continue

            published_raw = post.get("published_at") or post.get("created_at")
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

            items.append(
                NewsItem(
                    id_hash=news_hash(link),
                    title=title[:300],
                    url=link,
                    source=self.name,
                    source_label=self.source_label,
                    published_at=published_at.astimezone(timezone.utc),
                    summary=None,
                    author=None,
                )
            )
        log.info("[%s] fetched %d items", self.name, len(items))
        return items