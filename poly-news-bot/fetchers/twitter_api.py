"""Twitter/X official API fetcher (optional, requires bearer token)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp
from dateutil import parser as date_parser

from utils.hashing import fallback_hash
from utils.http import fetch_json

from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


class TwitterApiFetcher(BaseFetcher):
    name = "twitter_api"
    source_label = "X (API)"

    def __init__(self, bearer_token: str) -> None:
        self.bearer_token = bearer_token

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        params = {
            "query": "Polymarket OR from:Polymarket",
            "max_results": "30",
            "tweet.fields": "created_at,author_id,text",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        try:
            data = await fetch_json(
                session, SEARCH_URL, headers=headers, params=params
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []

        users_by_id: dict[str, dict] = {}
        includes = data.get("includes", {}) if isinstance(data, dict) else {}
        for u in includes.get("users", []) or []:
            users_by_id[u["id"]] = u

        items: list[NewsItem] = []
        for tw in data.get("data", []) if isinstance(data, dict) else []:
            text = tw.get("text") or ""
            tid = tw.get("id")
            if not tid or not text:
                continue
            author_id = tw.get("author_id")
            user = users_by_id.get(author_id or "", {})
            username = user.get("username") or "i"
            url = f"https://twitter.com/{username}/status/{tid}"
            created_raw = tw.get("created_at")
            try:
                created = (
                    date_parser.parse(created_raw)
                    if created_raw
                    else datetime.now(timezone.utc)
                )
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                created = datetime.now(timezone.utc)
            items.append(
                NewsItem(
                    id_hash=fallback_hash(
                        self.name, username, text[:80], created.date().isoformat()
                    ),
                    title=text[:200],
                    url=url,
                    source=self.name,
                    source_label=self.source_label,
                    published_at=created.astimezone(timezone.utc),
                    summary=text,
                    author=username,
                )
            )
        log.info("[%s] fetched %d items", self.name, len(items))
        return items