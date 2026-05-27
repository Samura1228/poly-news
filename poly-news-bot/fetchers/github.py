"""GitHub fetcher: surface notable Polymarket org events (releases, pushes, tags)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp
from dateutil import parser as date_parser

from utils.hashing import fallback_hash, news_hash
from utils.http import fetch_json

from .base import BaseFetcher, NewsItem

log = logging.getLogger(__name__)

EVENTS_URL = "https://api.github.com/orgs/Polymarket/events/public"

_INTERESTING_EVENTS = {"ReleaseEvent", "PushEvent", "CreateEvent"}


class GitHubFetcher(BaseFetcher):
    name = "github"
    source_label = "GitHub — Polymarket"

    def __init__(self, token: str = "") -> None:
        self.token = (token or "").strip()

    async def fetch(self, session: aiohttp.ClientSession) -> list[NewsItem]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            data = await fetch_json(session, EVENTS_URL, headers=headers)
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] error: %s", self.name, e)
            return []
        if not isinstance(data, list):
            return []
        items: list[NewsItem] = []
        for ev in data:
            etype = ev.get("type")
            if etype not in _INTERESTING_EVENTS:
                continue
            item = self._event_to_item(ev, etype)
            if item:
                items.append(item)
        log.info("[%s] fetched %d items", self.name, len(items))
        return items

    def _event_to_item(self, ev: dict[str, Any], etype: str) -> NewsItem | None:
        repo = (ev.get("repo") or {}).get("name") or "Polymarket"
        actor = (ev.get("actor") or {}).get("login")
        created_raw = ev.get("created_at")
        try:
            created = (
                date_parser.parse(created_raw)
                if created_raw
                else datetime.now(timezone.utc)
            )
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            created = datetime.now(timezone.utc)

        payload = ev.get("payload") or {}
        if etype == "ReleaseEvent":
            rel = payload.get("release") or {}
            url = rel.get("html_url") or f"https://github.com/{repo}/releases"
            title = f"{repo}: release {rel.get('tag_name') or rel.get('name') or ''}".strip()
            summary = rel.get("body")
            id_hash = news_hash(url)
        elif etype == "PushEvent":
            ref = payload.get("ref") or ""
            # Only surface pushes to default-looking branches.
            if not (ref.endswith("/main") or ref.endswith("/master")):
                return None
            commits = payload.get("commits") or []
            url = f"https://github.com/{repo}/commits/{ref.split('/')[-1]}"
            title = f"{repo}: {len(commits)} commit(s) to {ref.split('/')[-1]}"
            summary = "\n".join(
                c.get("message", "").splitlines()[0] for c in commits[:5]
            )
            id_hash = fallback_hash(
                self.name, actor, title, created.isoformat()
            )
        elif etype == "CreateEvent":
            if payload.get("ref_type") != "tag":
                return None
            tag = payload.get("ref") or ""
            url = f"https://github.com/{repo}/releases/tag/{tag}"
            title = f"{repo}: tag {tag}"
            summary = None
            id_hash = news_hash(url)
        else:
            return None

        return NewsItem(
            id_hash=id_hash,
            title=title[:300],
            url=url,
            source=self.name,
            source_label=self.source_label,
            published_at=created.astimezone(timezone.utc),
            summary=summary,
            author=actor,
        )