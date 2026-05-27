"""Generic keyword-filtered RSS fetcher used for crypto-news outlets."""
from __future__ import annotations

import logging

import aiohttp

from utils.keyword_filter import matches_polymarket

from ._rss_helpers import fetch_feed_items
from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)


class RssGenericFetcher(BaseFetcher):
    """Fetch an RSS feed and keep only entries mentioning Polymarket."""

    def __init__(self, name: str, source_label: str, feed_url: str) -> None:
        self.name = name
        self.source_label = source_label
        self.feed_url = feed_url

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        try:
            raw = await fetch_feed_items(
                session,
                self.feed_url,
                source=self.name,
                source_label=self.source_label,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []
        filtered = [
            item
            for item in raw
            if matches_polymarket(f"{item.title}\n{item.summary or ''}")
        ]
        log.info(
            "[%s] fetched %d items (%d after keyword filter)",
            self.name,
            len(raw),
            len(filtered),
        )
        return filtered


# Curated set of crypto/finance outlets to filter for Polymarket mentions.
# (RSS URLs sourced from ARCHITECTURE.md §1.)
GENERIC_RSS_FEEDS: list[tuple[str, str, str]] = [
    ("coindesk", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("cointelegraph", "CoinTelegraph", "https://cointelegraph.com/rss"),
    ("decrypt", "Decrypt", "https://decrypt.co/feed"),
    ("theblock", "The Block", "https://www.theblock.co/rss.xml"),
    ("thedefiant", "The Defiant", "https://thedefiant.io/api/feed"),
    ("bankless", "Bankless", "https://newsletter.banklesshq.com/feed"),
    ("blockworks", "Blockworks", "https://blockworks.co/feed"),
    ("coinjournal", "CoinJournal", "https://coinjournal.net/news/feed/"),
    ("cryptoslate", "CryptoSlate", "https://cryptoslate.com/feed/"),
    ("protos", "Protos", "https://protos.com/feed/"),
    ("medium_polymarket", "Medium (polymarket tag)", "https://medium.com/feed/tag/polymarket"),
    (
        "yahoo_finance",
        "Yahoo Finance",
        "https://finance.yahoo.com/rss/headline?s=polymarket",
    ),
    (
        "prnewswire",
        "PR Newswire",
        "https://www.prnewswire.com/rss/news-releases-list.rss",
    ),
    # DefiLlama exposes a news page; the RSS endpoint may not always exist —
    # we include the JSON endpoint URL via the generic fetcher only if it
    # responds with feed-like content; if it doesn't, feedparser will return [].
    ("defillama", "DefiLlama", "https://defillama.com/news/rss.xml"),
]


def build_generic_fetchers(disabled: set[str]) -> list[RssGenericFetcher]:
    """Instantiate generic RSS fetchers, skipping any whose slug is disabled."""
    fetchers: list[RssGenericFetcher] = []
    for name, label, url in GENERIC_RSS_FEEDS:
        if name in disabled:
            continue
        fetchers.append(RssGenericFetcher(name=name, source_label=label, feed_url=url))
    return fetchers