"""Entry point: build the Telegram Application, wire commands, start scheduler."""
from __future__ import annotations

import asyncio
import html
import logging
import time
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from config import Settings
from fetchers import get_enabled_fetchers
from scheduler import NewsScheduler
from storage import Storage
from utils.formatter import format_news_item

log = logging.getLogger(__name__)

_START_TIME = time.monotonic()
_WELCOME = (
    "👋 <b>Welcome to the Polymarket News Bot</b>\n\n"
    "I'll send you the latest Polymarket-related news from across the web, "
    "every {interval} minutes.\n\n"
    "<b>Commands</b>\n"
    "/start — subscribe to updates\n"
    "/stop — unsubscribe\n"
    "/status — your subscription status\n"
    "/sources — list news sources I'm watching\n"
    "/last — show the 5 most recent news items\n"
    "/help — show this help\n"
)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Tame noisy 3rd-party loggers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("telegram.ext.Application").setLevel(logging.INFO)


# --- Command handlers ---


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    settings: Settings = context.application.bot_data["settings"]
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return
    username = (user.username if user else None) or (user.full_name if user else None)
    newly = await storage.add_subscriber(chat.id, username)
    msg = _WELCOME.format(interval=settings.poll_interval_minutes)
    if not newly:
        msg = "✅ You're already subscribed.\n\n" + msg
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    chat = update.effective_chat
    if not chat:
        return
    changed = await storage.remove_subscriber(chat.id)
    if changed:
        await update.message.reply_text(
            "👋 Unsubscribed. Send /start any time to resume."
        )
    else:
        await update.message.reply_text(
            "ℹ️ You weren't subscribed. Send /start to subscribe."
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    settings: Settings = context.application.bot_data["settings"]
    chat = update.effective_chat
    if not chat:
        return
    info = await storage.get_subscriber_info(chat.id)
    delivered = await storage.count_delivered(chat.id)
    active = await storage.count_active_subscribers()
    if info is None:
        text = (
            "📊 <b>Status</b>\n"
            "Not subscribed yet. Send /start to begin.\n"
            f"Active subscribers: {active}"
        )
    else:
        state = "active ✅" if info.get("active") else "inactive ⏸"
        joined = info.get("joined_at") or "—"
        text = (
            "📊 <b>Your status</b>\n"
            f"State: {state}\n"
            f"Joined: <code>{html.escape(str(joined))}</code>\n"
            f"Messages delivered: <b>{delivered}</b>\n"
            f"Poll interval: every <b>{settings.poll_interval_minutes}</b> min\n"
            f"Total active subscribers: <b>{active}</b>"
        )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    fetchers = context.application.bot_data["fetchers"]
    lines = ["📡 <b>Enabled news sources</b>"]
    for f in fetchers:
        lines.append(
            f"• <b>{html.escape(f.source_label)}</b> "
            f"<code>({html.escape(f.name)})</code>"
        )
    lines.append("")
    lines.append(f"Total: <b>{len(fetchers)}</b>")
    # Telegram messages cap at 4096 chars — chunk if needed.
    text = "\n".join(lines)
    for chunk in _chunk_text(text, 3800):
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    await update.message.reply_text(
        _WELCOME.format(interval=settings.poll_interval_minutes),
        parse_mode=ParseMode.HTML,
    )


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    args = context.args or []
    n = 5
    if args:
        try:
            n = max(1, min(20, int(args[0])))
        except ValueError:
            pass
    items = await storage.get_recent_news(n)
    if not items:
        await update.message.reply_text(
            "No news in storage yet. The first cycle will populate it shortly."
        )
        return
    for item in items:
        try:
            await update.message.reply_text(
                format_news_item(item),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
            await asyncio.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            log.warning("cmd_last send error: %s", e)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uptime_s = int(time.monotonic() - _START_TIME)
    h, rem = divmod(uptime_s, 3600)
    m, s = divmod(rem, 60)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await update.message.reply_text(
        f"pong 🏓\nuptime: {h:02d}h{m:02d}m{s:02d}s\nutc: {now}"
    )


def _chunk_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    while text:
        out.append(text[:limit])
        text = text[limit:]
    return out


# --- Lifecycle hooks ---


async def _post_init(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    storage = Storage(settings.database_path)
    await storage.connect()
    fetchers = get_enabled_fetchers(settings)

    application.bot_data["storage"] = storage
    application.bot_data["fetchers"] = fetchers

    scheduler = NewsScheduler(application, storage, fetchers, settings)
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    log.info("post_init complete; %d fetchers enabled", len(fetchers))


async def _post_shutdown(application: Application) -> None:
    sched: NewsScheduler | None = application.bot_data.get("scheduler")
    if sched:
        sched.shutdown()
    storage: Storage | None = application.bot_data.get("storage")
    if storage:
        await storage.close()
    log.info("shutdown complete")


def build_application(settings: Settings) -> Application:
    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("last", cmd_last))
    app.add_handler(CommandHandler("ping", cmd_ping))
    return app


def main() -> None:
    settings = Settings.load()
    _configure_logging(settings.log_level)
    log.info("starting Polymarket news bot")
    app = build_application(settings)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()