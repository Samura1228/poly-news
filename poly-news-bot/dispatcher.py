"""Dispatcher: deliver pre-built digests to subscribers.

The scheduler builds digests once per cycle (see :mod:`summarizer`) and then
calls :func:`fanout` to broadcast them. Per-subscriber gating is by
``last_digest_sent_at`` — a subscriber receives at most one batch of digests
per cycle, even across restarts.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TelegramError

from fetchers.base import NewsItem
from storage import Storage
from summarizer import Digest

log = logging.getLogger(__name__)

# Telegram global limit is ~30 msg/sec across all chats. Pace around 10/sec to
# leave plenty of headroom — digests are large and we send at most ~3/cycle.
SEND_SLEEP_SECONDS = 0.1


async def fanout(
    bot: Bot,
    storage: Storage,
    digests: list[Digest],
    fresh_items: list[NewsItem],
    cycle_started_at: datetime,
) -> int:
    """Broadcast *digests* to every active subscriber that hasn't seen this cycle.

    Returns the number of subscribers that received at least one digest.
    Each subscriber:
      * is skipped if ``last_digest_sent_at >= cycle_started_at``;
      * otherwise gets all digests (image first → caption; else text);
      * has all *fresh_items* marked seen on success (best-effort);
      * has ``last_digest_sent_at`` updated after a successful send.
    """
    if not digests:
        log.info("fanout: no digests to send this cycle")
        return 0

    subscribers = await storage.list_subscribers(active_only=True)
    if not subscribers:
        log.info("fanout: no active subscribers")
        return 0

    fresh_hashes = [it.id_hash for it in fresh_items]
    reached = 0

    for chat_id in subscribers:
        # Per-cycle gating.
        try:
            last = await storage.get_last_digest_sent_at(chat_id)
        except Exception as e:  # noqa: BLE001
            log.warning("fanout: get_last_digest_sent_at failed for %s: %s", chat_id, e)
            last = None
        if last is not None and last >= cycle_started_at:
            log.debug("fanout: skipping %s (already received this cycle)", chat_id)
            continue

        sent_any = False
        stop_user = False
        for digest in digests:
            try:
                if digest.image_url:
                    try:
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=digest.image_url,
                            caption=digest.text,
                            parse_mode=ParseMode.HTML,
                        )
                    except Forbidden:
                        raise
                    except Exception as photo_err:  # noqa: BLE001
                        log.warning(
                            "send_photo failed for %s (%s); retrying as text",
                            chat_id,
                            photo_err,
                        )
                        await bot.send_message(
                            chat_id=chat_id,
                            text=digest.text,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=digest.text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                sent_any = True
                await asyncio.sleep(SEND_SLEEP_SECONDS)
            except Forbidden:
                log.info(
                    "user %s blocked the bot — deactivating subscription", chat_id
                )
                try:
                    await storage.remove_subscriber(chat_id)
                except Exception:  # noqa: BLE001
                    pass
                stop_user = True
                break
            except RetryAfter as e:
                wait_s = float(getattr(e, "retry_after", 5))
                log.warning(
                    "Telegram rate limit hit for %s; sleeping %.1fs", chat_id, wait_s
                )
                await asyncio.sleep(wait_s + 0.5)
            except TelegramError as e:
                log.warning("send to %s failed: %s", chat_id, e)
            except Exception as e:  # noqa: BLE001
                log.warning("unexpected send error to %s: %s", chat_id, e)

        if stop_user:
            continue

        if sent_any:
            reached += 1
            # Mark all fresh items as seen for this user so /last + future
            # cycle dedup work correctly.
            if fresh_hashes:
                try:
                    await storage.mark_seen(chat_id, fresh_hashes)
                except Exception as e:  # noqa: BLE001
                    log.warning("mark_seen failed for %s: %s", chat_id, e)
            try:
                await storage.update_last_digest_sent_at(chat_id, cycle_started_at)
            except Exception as e:  # noqa: BLE001
                log.warning("update_last_digest_sent_at failed for %s: %s", chat_id, e)

    log.info(
        "fanout complete: %d/%d subscribers received this cycle's digests",
        reached,
        len(subscribers),
    )
    return reached