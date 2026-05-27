"""Shared helpers for parsing RSS/Atom feeds via feedparser."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp
import feedparser
from dateutil import parser as date_parser

from utils.hashing import news_hash
from utils.http import fetch_bytes

from .base import NewsItem

log = logging.getLogger(__name__)


def _parse_dt(entry: dict[str, Any]) -> datetime:
    """Best-effort published-at extraction; falls back to now()."""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        val = entry.get(key)
        if val:
            try:
                return datetime.fromtimestamp(time.mktime(val), tz=timezone.utc)
            except Exception:  # noqa: BLE001
                pass
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if raw:
            try:
                dt = date_parser.parse(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:  # noqa: BLE001
                pass
    return datetime.now(timezone.utc)


def _entry_summary(entry: dict[str, Any]) -> Optional[str]:
    for key in ("summary", "description", "subtitle"):
        val = entry.get(key)
        if val:
            return str(val)
    content = entry.get("content")
    if isinstance(content, list) and content:
        try:
            return str(content[0].get("value"))
        except Exception:  # noqa: BLE001
            pass
    return None


def _entry_author(entry: dict[str, Any]) -> Optional[str]:
    val = entry.get("author")
    if val:
        return str(val)
    authors = entry.get("authors")
    if isinstance(authors, list) and authors:
        try:
            return str(authors[0].get("name"))
        except Exception:  # noqa: BLE001
            pass
    return None


def feed_to_items(
    raw_bytes: bytes,
    *,
    source: str,
    source_label: str,
) -> list[NewsItem]:
    """Parse raw feed bytes into NewsItem list. Synchronous (call inside to_thread)."""
    parsed = feedparser.parse(raw_bytes)
    items: list[NewsItem] = []
    for entry in parsed.entries or []:
        link = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        if not link or not title:
            continue
        try:
            item = NewsItem(
                id_hash=news_hash(link),
                title=title,
                url=link,
                source=source,
                source_label=source_label,
                published_at=_parse_dt(entry),
                summary=_entry_summary(entry),
                author=_entry_author(entry),
            )
            items.append(item)
        except Exception as e:  # noqa: BLE001
            log.debug("skipping malformed entry for %s: %s", source, e)
    return items


async def fetch_feed_items(
    session: aiohttp.ClientSession,
    url: str,
    *,
    source: str,
    source_label: str,
    headers: Optional[dict[str, str]] = None,
) -> list[NewsItem]:
    """Fetch + parse an RSS/Atom feed asynchronously.

    HTTP is via aiohttp; feedparser runs in a worker thread so we don't block
    the event loop.
    """
    raw = await fetch_bytes(session, url, headers=headers)
    return await asyncio.to_thread(
        feed_to_items, raw, source=source, source_label=source_label
    )