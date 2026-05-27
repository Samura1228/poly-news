"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_str(name: str, default: str = "") -> str:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip()


def _get_csv(name: str, default: Optional[List[str]] = None) -> List[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return list(default or [])
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass
class Settings:
    # Required
    telegram_bot_token: str

    # Polling
    poll_interval_minutes: int = 30
    startup_delay_seconds: int = 30
    backfill_window_hours: int = 24
    max_items_per_cycle: int = 10

    # Storage
    database_path: str = "./data/bot.db"
    news_retention_days: int = 30

    # HTTP
    http_timeout_seconds: int = 20
    http_user_agent: str = "PolyNewsBot/1.0 (+https://t.me/your_bot)"

    # Optional credentials
    cryptopanic_api_key: str = ""
    cryptopanic_api_plan: str = "developer"
    newsdata_api_key: str = ""
    mediastack_api_key: str = ""
    twitter_bearer_token: str = ""
    github_token: str = ""

    # Source toggles
    disabled_sources: List[str] = field(default_factory=list)

    # Nitter
    nitter_mirrors: List[str] = field(
        default_factory=lambda: ["nitter.net", "nitter.poast.org", "nitter.privacydev.net"]
    )

    # YouTube
    polymarket_youtube_channel_id: str = ""

    # Logging
    log_level: str = "INFO"

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        token = _get_str("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is required. Copy .env.example to .env and set it."
            )
        return cls(
            telegram_bot_token=token,
            poll_interval_minutes=_get_int("POLL_INTERVAL_MINUTES", 30),
            startup_delay_seconds=_get_int("STARTUP_DELAY_SECONDS", 30),
            backfill_window_hours=_get_int("BACKFILL_WINDOW_HOURS", 24),
            max_items_per_cycle=_get_int("MAX_ITEMS_PER_CYCLE", 10),
            database_path=_get_str("DATABASE_PATH", "./data/bot.db"),
            news_retention_days=_get_int("NEWS_RETENTION_DAYS", 30),
            http_timeout_seconds=_get_int("HTTP_TIMEOUT_SECONDS", 20),
            http_user_agent=_get_str(
                "HTTP_USER_AGENT", "PolyNewsBot/1.0 (+https://t.me/your_bot)"
            ),
            cryptopanic_api_key=_get_str("CRYPTOPANIC_API_KEY"),
            cryptopanic_api_plan=_get_str("CRYPTOPANIC_API_PLAN", "developer") or "developer",
            newsdata_api_key=_get_str("NEWSDATA_API_KEY"),
            mediastack_api_key=_get_str("MEDIASTACK_API_KEY"),
            twitter_bearer_token=_get_str("TWITTER_BEARER_TOKEN"),
            github_token=_get_str("GITHUB_TOKEN"),
            disabled_sources=_get_csv("DISABLED_SOURCES"),
            nitter_mirrors=_get_csv(
                "NITTER_MIRRORS",
                default=["nitter.net", "nitter.poast.org", "nitter.privacydev.net"],
            ),
            polymarket_youtube_channel_id=_get_str("POLYMARKET_YOUTUBE_CHANNEL_ID"),
            log_level=_get_str("LOG_LEVEL", "INFO").upper(),
        )