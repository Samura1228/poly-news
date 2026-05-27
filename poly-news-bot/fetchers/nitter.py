"""Nitter (Twitter/X mirror) fetcher with multi-mirror failover."""
from __future__ import annotations

import logging
from typing import Iterable

import aiohttp

from ._rss_helpers import fetch_feed_items
from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

POLYMARKET_HANDLE = "Polymarket"


class NitterFetcher(BaseFetcher):
    name = "nitter"
    source_label = "X (via Nitter)"

    def __init__(self, mirrors: Iterable[str]) -> None:
        # Sanitize: drop empties, strip trailing slashes and scheme.
        cleaned: list[str] = []
        for m in mirrors:
            m = (m or "").strip()
            if not m:
                continue
            if m.startswith("http://") or m.startswith("https://"):
                m = m.split("://", 1)[1]
            m = m.rstrip("/")
            cleaned.append(m)
        self.mirrors = cleaned

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        if not self.mirrors:
            log.info("[%s] no mirrors configured; skipping", self.name)
            return []
        last_err: Exception | None = None
        for host in self.mirrors:
            url = f"https://{host}/{POLYMARKET_HANDLE}/rss"
            try:
                items = await fetch_feed_items(
                    session,
                    url,
                    source=self.name,
                    source_label=self.source_label,
                )
                if items:
                    log.info(
                        "[%s] fetched %d items via %s", self.name, len(items), host
                    )
                    return items
                # Empty feed: try next mirror.
                log.debug("[%s] empty feed from %s, trying next", self.name, host)
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.debug("[%s] mirror %s failed: %s", self.name, host, e)
        log.warning(
            "[%s] all mirrors failed (last error: %s); returning []",
            self.name,
            last_err,
        )
        return []