"""APScheduler wiring: poll every N minutes + an immediate startup catchup."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram.ext import Application

from aggregator import collect_all_news
from config import Settings
from dispatcher import fanout
from fetchers import BaseFetcher
from storage import Storage
from utils.http import build_session

log = logging.getLogger(__name__)


class NewsScheduler:
    def __init__(
        self,
        application: Application,
        storage: Storage,
        fetchers: list[BaseFetcher],
        settings: Settings,
    ) -> None:
        self.application = application
        self.storage = storage
        self.fetchers = fetchers
        self.settings = settings
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    async def _run_cycle(self) -> None:
        log.info("=== news cycle starting ===")
        try:
            async with build_session(
                user_agent=self.settings.http_user_agent,
                timeout_seconds=self.settings.http_timeout_seconds,
            ) as session:
                items = await collect_all_news(
                    session,
                    self.fetchers,
                    max_items=None,  # cap is per-user; we keep all for storage
                )
            new_count = await self.storage.upsert_news(items)
            log.info(
                "cycle persisted: fetched=%d new_global=%d", len(items), new_count
            )
            await fanout(
                self.application.bot,
                self.storage,
                backfill_window_hours=self.settings.backfill_window_hours,
                max_items_per_cycle=self.settings.max_items_per_cycle,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("news cycle crashed: %s", e)
        finally:
            log.info("=== news cycle complete ===")

    async def _run_prune(self) -> None:
        try:
            deleted = await self.storage.prune(self.settings.news_retention_days)
            if deleted:
                log.info("pruned %d news rows older than %d days",
                         deleted, self.settings.news_retention_days)
        except Exception as e:  # noqa: BLE001
            log.warning("prune failed: %s", e)

    def start(self) -> None:
        # Recurring cycle.
        self.scheduler.add_job(
            self._run_cycle,
            trigger=IntervalTrigger(minutes=self.settings.poll_interval_minutes),
            id="news_cycle",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Startup catchup ~STARTUP_DELAY_SECONDS after boot.
        first_run = datetime.now(timezone.utc) + timedelta(
            seconds=max(5, self.settings.startup_delay_seconds)
        )
        self.scheduler.add_job(
            self._run_cycle,
            trigger="date",
            run_date=first_run,
            id="news_cycle_initial",
            replace_existing=True,
        )
        # Daily prune.
        self.scheduler.add_job(
            self._run_prune,
            trigger=IntervalTrigger(hours=24),
            id="news_prune",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        log.info(
            "scheduler started: poll every %d min; first cycle at %s",
            self.settings.poll_interval_minutes,
            first_run.isoformat(),
        )

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)