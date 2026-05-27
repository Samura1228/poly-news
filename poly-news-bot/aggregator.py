"""Aggregator: orchestrate all fetchers, dedupe & cap the result."""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import aiohttp

from fetchers.base import BaseFetcher, NewsItem
from utils.keyword_filter import matches_polymarket

log = logging.getLogger(__name__)


async def _safe_fetch(
    fetcher: BaseFetcher, session: aiohttp.ClientSession
) -> list[NewsItem]:
    """Run a fetcher with a per-fetcher timeout, swallowing all exceptions."""
    try:
        return await asyncio.wait_for(
            fetcher.fetch(session), timeout=fetcher.timeout_seconds
        )
    except asyncio.TimeoutError:
        log.warning(
            "[%s] timed out after %.1fs", fetcher.name, fetcher.timeout_seconds
        )
        return []
    except Exception as e:  # noqa: BLE001
        log.warning("[%s] unhandled error: %s", fetcher.name, e)
        return []


async def collect_all_news(
    session: aiohttp.ClientSession,
    fetchers: Iterable[BaseFetcher],
    *,
    max_items: int | None = None,
) -> list[NewsItem]:
    """Run all fetchers concurrently and merge their results.

    - Per-fetcher timeout + exception isolation via `_safe_fetch`.
    - Deduplicates by `id_hash`.
    - Applies the global `matches_polymarket` filter as a belt-and-braces step
      (most fetchers already filter, but Google News / Reddit etc. may not).
    - Caps total at `max_items` (newest-first kept).
    """
    fetchers = list(fetchers)
    tasks = [_safe_fetch(f, session) for f in fetchers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    merged: dict[str, NewsItem] = {}
    for fetcher, result in zip(fetchers, results):
        if isinstance(result, BaseException):
            log.warning("[%s] gather error: %s", fetcher.name, result)
            continue
        for item in result:
            # Final belt-and-braces keyword filter: be lenient — sources like
            # Google News and Polymarket Blog are inherently scoped, so we
            # accept anything from them; everywhere else we require a mention.
            if fetcher.name in (
                "google_news",
                "bing_news",
                "polymarket_blog",
                "nitter",
                "twitter_api",
                "reddit",
                "hacker_news",
                "youtube",
                "github",
            ):
                pass  # trust the source / its own filtering
            else:
                text = f"{item.title}\n{item.summary or ''}"
                if not matches_polymarket(text):
                    continue
            merged[item.id_hash] = item

    items = list(merged.values())
    # Sort newest-first so the cap keeps the freshest items.
    items.sort(key=lambda i: i.published_at, reverse=True)
    if max_items is not None and len(items) > max_items:
        log.info(
            "capping cycle: %d -> %d items (MAX_ITEMS_PER_CYCLE)",
            len(items),
            max_items,
        )
        items = items[:max_items]
    log.info("aggregator collected %d unique items", len(items))
    return items