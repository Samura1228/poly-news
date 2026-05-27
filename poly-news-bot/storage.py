"""Async SQLite persistence layer for subscribers, news, and seen_news."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterable, Optional

import aiosqlite

from fetchers.base import NewsItem

log = logging.getLogger(__name__)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id     INTEGER PRIMARY KEY,
    username    TEXT,
    joined_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active      INTEGER NOT NULL DEFAULT 1,
    stopped_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news (
    news_hash     TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL,
    source        TEXT NOT NULL,
    source_label  TEXT NOT NULL,
    published_at  TIMESTAMP NOT NULL,
    summary       TEXT,
    author        TEXT,
    first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_news_first_seen ON news(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_news_source ON news(source);

CREATE TABLE IF NOT EXISTS seen_news (
    news_hash  TEXT NOT NULL,
    chat_id    INTEGER NOT NULL,
    sent_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (news_hash, chat_id),
    FOREIGN KEY (news_hash) REFERENCES news(news_hash),
    FOREIGN KEY (chat_id)   REFERENCES subscribers(chat_id)
);
CREATE INDEX IF NOT EXISTS idx_seen_chat ON seen_news(chat_id);
"""


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        # Be tolerant: aiosqlite may give us "YYYY-MM-DD HH:MM:SS" too.
        if "T" in raw:
            dt = datetime.fromisoformat(raw)
        else:
            dt = datetime.fromisoformat(raw.replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


class Storage:
    """Async SQLite wrapper for the bot's persistent state."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA_SQL)
        await self._conn.commit()
        log.info("storage connected at %s", self.db_path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Storage not connected. Call await storage.connect() first.")
        return self._conn

    # ----- Subscribers -----

    async def add_subscriber(self, chat_id: int, username: str | None = None) -> bool:
        """Insert or reactivate a subscriber. Returns True if newly subscribed."""
        async with self.conn.execute(
            "SELECT active FROM subscribers WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            await self.conn.execute(
                "INSERT INTO subscribers (chat_id, username, active) VALUES (?, ?, 1)",
                (chat_id, username),
            )
            await self.conn.commit()
            return True
        if row["active"] == 0:
            await self.conn.execute(
                "UPDATE subscribers SET active = 1, stopped_at = NULL, username = COALESCE(?, username) "
                "WHERE chat_id = ?",
                (username, chat_id),
            )
            await self.conn.commit()
            return True
        # Already active; just refresh username.
        if username:
            await self.conn.execute(
                "UPDATE subscribers SET username = ? WHERE chat_id = ?",
                (username, chat_id),
            )
            await self.conn.commit()
        return False

    async def remove_subscriber(self, chat_id: int) -> bool:
        """Deactivate a subscriber. Returns True if state changed."""
        async with self.conn.execute(
            "SELECT active FROM subscribers WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or row["active"] == 0:
            return False
        await self.conn.execute(
            "UPDATE subscribers SET active = 0, stopped_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            (chat_id,),
        )
        await self.conn.commit()
        return True

    async def list_subscribers(self, *, active_only: bool = True) -> list[int]:
        sql = "SELECT chat_id FROM subscribers"
        if active_only:
            sql += " WHERE active = 1"
        async with self.conn.execute(sql) as cur:
            rows = await cur.fetchall()
        return [int(r["chat_id"]) for r in rows]

    async def is_subscribed(self, chat_id: int) -> bool:
        async with self.conn.execute(
            "SELECT active FROM subscribers WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        return bool(row and row["active"] == 1)

    async def get_subscriber_info(self, chat_id: int) -> dict | None:
        async with self.conn.execute(
            "SELECT chat_id, username, joined_at, active, stopped_at "
            "FROM subscribers WHERE chat_id = ?",
            (chat_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return dict(row)

    async def count_active_subscribers(self) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) AS n FROM subscribers WHERE active = 1"
        ) as cur:
            row = await cur.fetchone()
        return int(row["n"]) if row else 0

    async def count_delivered(self, chat_id: int) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) AS n FROM seen_news WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        return int(row["n"]) if row else 0

    # ----- News -----

    async def upsert_news(self, items: Iterable[NewsItem]) -> int:
        """INSERT OR IGNORE a batch of NewsItems. Returns count of newly inserted rows."""
        items = list(items)
        if not items:
            return 0
        rows = [
            (
                it.id_hash,
                it.title,
                it.url,
                it.source,
                it.source_label,
                _to_iso(it.published_at),
                it.summary,
                it.author,
            )
            for it in items
        ]
        # rowcount on executemany with INSERT OR IGNORE is unreliable across drivers;
        # compute the diff explicitly.
        before = await self._news_count()
        await self.conn.executemany(
            "INSERT OR IGNORE INTO news "
            "(news_hash, title, url, source, source_label, published_at, summary, author) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        await self.conn.commit()
        after = await self._news_count()
        return after - before

    async def _news_count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) AS n FROM news") as cur:
            row = await cur.fetchone()
        return int(row["n"]) if row else 0

    async def mark_seen(self, chat_id: int, news_hashes: Iterable[str]) -> None:
        rows = [(h, chat_id) for h in news_hashes]
        if not rows:
            return
        await self.conn.executemany(
            "INSERT OR IGNORE INTO seen_news (news_hash, chat_id) VALUES (?, ?)",
            rows,
        )
        await self.conn.commit()

    async def unseen_for_user(
        self, chat_id: int, since_dt: datetime
    ) -> list[NewsItem]:
        """Return NewsItems not yet delivered to this chat, within the backfill window."""
        since_iso = _to_iso(since_dt)
        sql = """
            SELECT n.news_hash, n.title, n.url, n.source, n.source_label,
                   n.published_at, n.summary, n.author
            FROM news n
            LEFT JOIN seen_news s
              ON s.news_hash = n.news_hash AND s.chat_id = ?
            WHERE s.news_hash IS NULL
              AND n.first_seen_at >= ?
            ORDER BY n.published_at ASC
        """
        async with self.conn.execute(sql, (chat_id, since_iso)) as cur:
            rows = await cur.fetchall()
        return [self._row_to_item(r) for r in rows]

    async def get_recent_news(self, limit: int = 5) -> list[NewsItem]:
        sql = """
            SELECT news_hash, title, url, source, source_label,
                   published_at, summary, author
            FROM news
            ORDER BY published_at DESC
            LIMIT ?
        """
        async with self.conn.execute(sql, (limit,)) as cur:
            rows = await cur.fetchall()
        return [self._row_to_item(r) for r in rows]

    @staticmethod
    def _row_to_item(row: aiosqlite.Row) -> NewsItem:
        return NewsItem(
            id_hash=row["news_hash"],
            title=row["title"],
            url=row["url"],
            source=row["source"],
            source_label=row["source_label"],
            published_at=_from_iso(row["published_at"]),
            summary=row["summary"],
            author=row["author"],
        )

    # ----- Maintenance -----

    async def prune(self, retention_days: int) -> int:
        """Delete news older than retention_days. Returns rows deleted."""
        async with self.conn.execute(
            "SELECT COUNT(*) AS n FROM news WHERE first_seen_at < datetime('now', ?)",
            (f"-{int(retention_days)} days",),
        ) as cur:
            row = await cur.fetchone()
        before = int(row["n"]) if row else 0
        await self.conn.execute(
            "DELETE FROM seen_news WHERE news_hash IN ("
            "  SELECT news_hash FROM news WHERE first_seen_at < datetime('now', ?)"
            ")",
            (f"-{int(retention_days)} days",),
        )
        await self.conn.execute(
            "DELETE FROM news WHERE first_seen_at < datetime('now', ?)",
            (f"-{int(retention_days)} days",),
        )
        await self.conn.commit()
        return before