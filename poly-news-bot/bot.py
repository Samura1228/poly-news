"""Entry point: build the Telegram Application, wire commands, start scheduler."""
from __future__ import annotations

import asyncio
import functools
import logging

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, Update
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

_WELCOME = (
    "👋 Welcome! You're subscribed to <b>Polymarket news digests</b>.\n\n"
    "Every hour I'll send you a short summary of the latest "
    "Polymarket-related news from across the web.\n\n"
    "<b>Commands</b>\n"
    "• /stop — unsubscribe\n"
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


# --- Admin guard ---


def admin_only(func):
    """Silently drop non-admin invocations."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings: Settings = context.application.bot_data["settings"]
        chat = update.effective_chat
        if (
            not settings.admin_chat_id
            or not chat
            or chat.id != settings.admin_chat_id
        ):
            return
        return await func(update, context)

    return wrapper


# --- Command handlers ---


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return
    username = (user.username if user else None) or (user.full_name if user else None)
    newly = await storage.add_subscriber(chat.id, username)
    msg = _WELCOME
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


@admin_only
async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import html as html_mod

    fetchers = context.application.bot_data["fetchers"]
    lines = ["📡 <b>Enabled news sources</b>"]
    for f in fetchers:
        lines.append(
            f"• <b>{html_mod.escape(f.source_label)}</b> "
            f"<code>({html_mod.escape(f.name)})</code>"
        )
    lines.append("")
    lines.append(f"Total: <b>{len(fetchers)}</b>")
    text = "\n".join(lines)
    for chunk in _chunk_text(text, 3800):
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


@admin_only
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
                disable_web_page_preview=True,
            )
            await asyncio.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            log.warning("cmd_last send error: %s", e)


def _chunk_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    while text:
        out.append(text[:limit])
        text = text[limit:]
    return out


# --- Lifecycle hooks ---


async def _set_command_menus(application: Application, settings: Settings) -> None:
    """Public menu: /start /stop. Admin chat additionally: /sources /last."""
    public = [
        BotCommand("start", "Subscribe to Polymarket news digests"),
        BotCommand("stop", "Unsubscribe"),
    ]
    admin = [
        BotCommand("start", "Subscribe to Polymarket news digests"),
        BotCommand("stop", "Unsubscribe"),
        BotCommand("sources", "List enabled news sources"),
        BotCommand("last", "Show the last digest"),
    ]
    try:
        await application.bot.set_my_commands(
            public, scope=BotCommandScopeDefault()
        )
    except Exception as e:  # noqa: BLE001
        log.warning("set_my_commands (default) failed: %s", e)
    if settings.admin_chat_id:
        try:
            await application.bot.set_my_commands(
                admin,
                scope=BotCommandScopeChat(chat_id=settings.admin_chat_id),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("set_my_commands (admin) failed: %s", e)


async def _post_init(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    storage = Storage(settings.database_path)
    await storage.connect()
    fetchers = get_enabled_fetchers(settings)

    application.bot_data["storage"] = storage
    application.bot_data["fetchers"] = fetchers

    await _set_command_menus(application, settings)

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

    # Public commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    # Admin-only (guard applied via @admin_only)
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("last", cmd_last))
    return app


def main() -> None:
    settings = Settings.load()
    _configure_logging(settings.log_level)
    log.info("starting Polymarket news bot")
    app = build_application(settings)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()