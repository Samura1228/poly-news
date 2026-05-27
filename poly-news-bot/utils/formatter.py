"""Format NewsItem instances as Telegram HTML messages."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from fetchers.base import NewsItem

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_MAX_TITLE = 250
_MAX_SUMMARY = 280


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    no_tags = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", no_tags).strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _time_ago(published_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    delta = now - published_at
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks}w ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    years = days // 365
    return f"{years}y ago"


def format_news_item(item: NewsItem) -> str:
    """Render a NewsItem as a Telegram-safe HTML string."""
    title = _truncate(_strip_html(item.title), _MAX_TITLE)
    summary = _truncate(_strip_html(item.summary or ""), _MAX_SUMMARY)
    source_label = item.source_label or item.source or "source"
    when = _time_ago(item.published_at)

    title_html = f"<b>{html.escape(title)}</b>"
    body_parts: list[str] = [title_html]
    if summary:
        body_parts.append(html.escape(summary))

    # URL must NOT be html-escaped inside href (it's a URL); but display label is escaped.
    link_html = (
        f'🔗 <a href="{html.escape(item.url, quote=True)}">'
        f"{html.escape(source_label)}</a> • {html.escape(when)}"
    )
    body_parts.append("")
    body_parts.append(link_html)
    return "\n".join(body_parts)