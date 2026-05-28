"""Best-effort image URL extraction for news items.

Two entry points:

* :func:`extract_image_from_feed_entry` — for feedparser entry dicts
  (media:thumbnail, media:content, enclosures, then HTML scrape of summary).
* :func:`extract_image_from_html` — for raw HTML strings (first <img src>).

Both return a URL string (must start with ``http``) or ``None``.
All errors are swallowed: missing images are routine, not exceptional.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


def _is_http_url(url: str | None) -> bool:
    if not url or not isinstance(url, str):
        return False
    return url.startswith("http://") or url.startswith("https://")


def extract_image_from_html(html: str) -> Optional[str]:
    """Return the first ``<img src="…">`` URL found in *html*, or None."""
    if not html or not isinstance(html, str):
        return None
    try:
        soup = BeautifulSoup(html, "lxml")
        img = soup.find("img")
        if img is None:
            return None
        src = img.get("src") or img.get("data-src")
        if isinstance(src, str):
            src = src.strip()
            if _is_http_url(src):
                return src
    except Exception as e:  # noqa: BLE001
        log.debug("extract_image_from_html failed: %s", e)
    return None


def extract_image_from_feed_entry(entry: Any) -> Optional[str]:
    """Pick the best image URL from a feedparser entry. Returns None on miss."""
    if entry is None:
        return None

    # 1. media:thumbnail
    try:
        thumbs = entry.get("media_thumbnail") if hasattr(entry, "get") else None
        if thumbs is None:
            thumbs = getattr(entry, "media_thumbnail", None)
        if thumbs and isinstance(thumbs, list):
            url = thumbs[0].get("url") if isinstance(thumbs[0], dict) else None
            if _is_http_url(url):
                return url
    except Exception as e:  # noqa: BLE001
        log.debug("media_thumbnail extract failed: %s", e)

    # 2. media:content
    try:
        contents = entry.get("media_content") if hasattr(entry, "get") else None
        if contents is None:
            contents = getattr(entry, "media_content", None)
        if contents and isinstance(contents, list):
            for c in contents:
                if isinstance(c, dict):
                    url = c.get("url")
                    if _is_http_url(url):
                        # Prefer image-typed entries but accept untyped.
                        mt = (c.get("type") or "").lower()
                        if not mt or mt.startswith("image/"):
                            return url
    except Exception as e:  # noqa: BLE001
        log.debug("media_content extract failed: %s", e)

    # 3. enclosures
    try:
        encs = entry.get("enclosures") if hasattr(entry, "get") else None
        if encs is None:
            encs = getattr(entry, "enclosures", None)
        if encs and isinstance(encs, list):
            for e in encs:
                if isinstance(e, dict):
                    mt = (e.get("type") or "").lower()
                    href = e.get("href") or e.get("url")
                    if _is_http_url(href) and (not mt or mt.startswith("image/")):
                        return href
    except Exception as ex:  # noqa: BLE001
        log.debug("enclosures extract failed: %s", ex)

    # 4. HTML scrape of summary / description / content
    candidates: list[str] = []
    for key in ("summary", "description"):
        try:
            val = entry.get(key) if hasattr(entry, "get") else getattr(entry, key, None)
            if isinstance(val, str) and val:
                candidates.append(val)
        except Exception:  # noqa: BLE001
            pass
    try:
        content = entry.get("content") if hasattr(entry, "get") else getattr(entry, "content", None)
        if isinstance(content, list) and content:
            v = content[0].get("value") if isinstance(content[0], dict) else None
            if isinstance(v, str) and v:
                candidates.append(v)
    except Exception:  # noqa: BLE001
        pass

    for html in candidates:
        url = extract_image_from_html(html)
        if url:
            return url

    return None