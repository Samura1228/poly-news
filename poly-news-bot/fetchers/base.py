"""Base classes and the NewsItem dataclass for all fetchers."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """A normalized news item from any source."""

    id_hash: str
    title: str
    url: str
    source: str
    source_label: str
    published_at: datetime
    summary: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None

    # Backwards-compat alias used in some places
    @property
    def id(self) -> str:  # noqa: D401
        return self.id_hash


class BaseFetcher(ABC):
    """Abstract base for all news fetchers."""

    # Short, lowercase machine-readable name (used in DB).
    name: str = "base"
    # Human-readable label (shown in `/sources` and Telegram messages).
    source_label: str = "Base"
    # Per-fetcher timeout (seconds) for one full fetch.
    timeout_seconds: float = 20.0

    @abstractmethod
    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        """Return a list of NewsItems. Must not raise; should log instead.

        However, the aggregator wraps invocations with try/except + timeout, so
        raising here is also acceptable — the cycle continues regardless.
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{self.__class__.__name__} name={self.name}>"