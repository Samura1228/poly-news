"""Dispatcher: per-subscriber filtering + paced Telegram delivery."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TelegramError

from storage import Storage
from utils.formatter import format_news_item

log = logging.getLogger(__name__)

# Telegram global limit is ~30 msg/sec across all chats. We pace at ~20/sec
# to keep headroom for retries.
SEND_SLEEP_SECONDS = 0.05


async def fanout(
    bot: Bot,
    storage: Storage,
    *,
    backfill_window_hours: int,
    max_items_per_cycle: int,
) -> int:
    """Deliver unseen news to every active subscriber.

    Returns the total number of messages successfully sent across all users.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=backfill_window_hours)
    subscribers = await storage.list_subscribers(active_only=True)
    if not subscribers:
        log.info("fanout: no active subscribers")
        return 0

    total_sent = 0
    for chat_id in subscribers:
        try:
            unseen = await storage.unseen_for_user(chat_id, cutoff)
        except Exception as e:  # noqa: BLE001
            log.warning("fanout: failed to query unseen for %s: %s", chat_id, e)
            continue
        if not unseen:
            continue
        # Cap per-user to avoid flooding (e.g. brand-new subscriber).
        batch = unseen[:max_items_per_cycle]
        sent_hashes: list[str] = []
        for item in batch:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=format_news_item(item),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
                sent_hashes.append(item.id_hash)
                total_sent += 1
                await asyncio.sleep(SEND_SLEEP_SECONDS)
            except Forbidden:
                log.info(
                    "user %s blocked the bot — deactivating subscription", chat_id
                )
                await storage.remove_subscriber(chat_id)
                break
            except RetryAfter as e:
                wait_s = float(getattr(e, "retry_after", 5))
                log.warning(
                    "Telegram rate limit hit for %s; sleeping %.1fs", chat_id, wait_s
                )
                await asyncio.sleep(wait_s + 0.5)
                # Don't mark seen for this one; will retry next cycle.
            except TelegramError as e:
                log.warning(
                    "send to %s failed for %s: %s", chat_id, item.id_hash, e
                )
                # Don't mark seen on transient errors; will retry next cycle.
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "unexpected send error to %s for %s: %s",
                    chat_id,
                    item.id_hash,
                    e,
                )
        if sent_hashes:
            try:
                await storage.mark_seen(chat_id, sent_hashes)
            except Exception as e:  # noqa: BLE001
                log.warning("failed to mark_seen for %s: %s", chat_id, e)
    log.info(
        "fanout complete: %d msgs sent across %d subscribers",
        total_sent,
        len(subscribers),
    )
    return total_sent