"""APScheduler wiring: hourly poll + startup catchup + daily prune."""
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
from summarizer import make_digests
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
        cycle_started_at = datetime.now(timezone.utc)
        log.info("=== news cycle starting (%s) ===", cycle_started_at.isoformat())
        try:
            async with build_session(
                user_agent=self.settings.http_user_agent,
                timeout_seconds=self.settings.http_timeout_seconds,
            ) as session:
                items = await collect_all_news(
                    session,
                    self.fetchers,
                    max_items=None,
                )

            # Freshness filter — anything older than MAX_NEWS_AGE_HOURS is dropped.
            cutoff = cycle_started_at - timedelta(
                hours=self.settings.max_news_age_hours
            )
            fresh: list = []
            for it in items:
                pa = it.published_at
                if pa is None:
                    continue
                if pa.tzinfo is None:
                    pa = pa.replace(tzinfo=timezone.utc)
                if pa >= cutoff:
                    fresh.append(it)

            log.info(
                "cycle: fetched=%d fresh=%d (within %dh)",
                len(items),
                len(fresh),
                self.settings.max_news_age_hours,
            )

            # Persist fresh items.
            new_count = await self.storage.upsert_news(fresh)
            log.info("cycle persisted: new_global=%d", new_count)

            if not fresh:
                log.info("no fresh items this cycle — nothing to summarize")
                return

            digests = await make_digests(fresh, self.settings)
            log.info("generated %d digest(s)", len(digests))

            if not digests:
                return

            await fanout(
                self.application.bot,
                self.storage,
                digests,
                fresh,
                cycle_started_at,
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