"""News digest generation: Anthropic Claude with a local rule-based fallback.

Public entry point is :func:`make_digests`. The module degrades gracefully:

* If the ``anthropic`` SDK is not installed, falls back to local digests.
* If ``ANTHROPIC_API_KEY`` is unset, falls back to local digests.
* If the Claude call raises (network, quota, parse error), falls back.

All user-facing text is Telegram-safe HTML.
"""
from __future__ import annotations

import html
import json
import logging
import math
import re
from dataclasses import dataclass
from typing import Optional

from config import Settings
from fetchers.base import NewsItem

log = logging.getLogger(__name__)

# Optional dependency — only required for the Claude path.
try:  # noqa: SIM105
    from anthropic import AsyncAnthropic  # type: ignore
except Exception:  # noqa: BLE001
    AsyncAnthropic = None  # type: ignore

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Telegram limits.
TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_TEXT_LIMIT = 4096
# Be conservative — leave headroom for HTML entities & rounding.
CAPTION_BUDGET = 1000
TEXT_BUDGET = 4000


@dataclass
class Digest:
    text: str
    image_url: Optional[str] = None


# --- Helpers ---------------------------------------------------------------


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    no_tags = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", no_tags).strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _unique_image_urls(items: list[NewsItem]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        url = (it.image_url or "").strip()
        if url and url.startswith("http") and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _assign_images(n_digests: int, images: list[str]) -> list[Optional[str]]:
    """Assign one image (or None) to each digest, in order."""
    out: list[Optional[str]] = []
    for i in range(n_digests):
        out.append(images[i] if i < len(images) else None)
    return out


def _enforce_budget(text: str, has_image: bool) -> str:
    budget = CAPTION_BUDGET if has_image else TEXT_BUDGET
    return _truncate(text, budget)


# --- Local fallback --------------------------------------------------------


def local_digest(items: list[NewsItem], settings: Settings) -> list[Digest]:
    if not items:
        return []

    max_msgs = max(1, int(settings.max_digest_messages or 3))
    # Roughly 5 items per digest.
    n = min(max_msgs, max(1, math.ceil(len(items) / 5)))
    chunk_size = math.ceil(len(items) / n)
    chunks: list[list[NewsItem]] = [
        items[i : i + chunk_size] for i in range(0, len(items), chunk_size)
    ]
    chunks = chunks[:n]

    images = _unique_image_urls(items)
    image_assignment = _assign_images(len(chunks), images)

    digests: list[Digest] = []
    for idx, chunk in enumerate(chunks):
        img = image_assignment[idx]
        lines: list[str] = ["📰 <b>Polymarket Hourly Digest</b>", ""]
        for it in chunk:
            title = _truncate(_strip_html(it.title), 220)
            summary = _truncate(_strip_html(it.summary or ""), 220)
            lines.append(f"<b>{html.escape(title)}</b>")
            if summary:
                lines.append(html.escape(summary))
            lines.append("")
        text = "\n".join(lines).rstrip()
        text = _enforce_budget(text, has_image=bool(img))
        digests.append(Digest(text=text, image_url=img))
    return digests


# --- Claude path -----------------------------------------------------------


_CLAUDE_SYSTEM = (
    "You write concise, factual crypto/prediction-market news digests for a "
    "Telegram bot. Output natural English prose, no URLs, no markdown links, "
    "no bullet lists in the prose. Group related stories. Each digest should "
    "feel like a paragraph of a news brief."
)


def _items_payload(items: list[NewsItem]) -> list[dict]:
    payload: list[dict] = []
    for it in items:
        payload.append(
            {
                "title": _truncate(_strip_html(it.title), 280),
                "source": it.source_label or it.source or "",
                "summary": _truncate(_strip_html(it.summary or ""), 600),
                "published_at": (
                    it.published_at.isoformat() if it.published_at else None
                ),
                "author": it.author or "",
            }
        )
    return payload


def _build_user_prompt(items: list[NewsItem], max_msgs: int) -> str:
    payload = _items_payload(items)
    instructions = (
        f"Below is a JSON array of {len(payload)} news items about Polymarket "
        "and related prediction-market / crypto topics, collected in the last "
        "hour.\n\n"
        "Write a news digest with these strict rules:\n"
        f"- Output AT MOST {max_msgs} digest message(s) (between 1 and "
        f"{max_msgs}).\n"
        "- Group similar stories together; merge duplicates.\n"
        "- Each digest is 2-4 short paragraphs of plain prose. No headers, "
        "no bullet lists, no markdown.\n"
        "- Do NOT include URLs or links of any kind.\n"
        "- Plain text only. At most ONE leading emoji per digest is allowed.\n"
        "- Each digest must fit comfortably under 900 characters.\n"
        "- Reply with strict JSON ONLY, no preamble: "
        '{"digests": [{"text": "..."}, ...]}\n\n'
        "News items JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    return instructions


def _parse_claude_json(raw: str) -> list[str]:
    """Extract the digest text strings from Claude's JSON reply."""
    # Be tolerant: sometimes a model wraps JSON in prose. Find the first {...}.
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in Claude reply")
    obj = json.loads(raw[start : end + 1])
    digests = obj.get("digests")
    if not isinstance(digests, list):
        raise ValueError("`digests` is not a list")
    out: list[str] = []
    for d in digests:
        if isinstance(d, dict):
            t = d.get("text")
            if isinstance(t, str) and t.strip():
                out.append(t.strip())
        elif isinstance(d, str) and d.strip():
            out.append(d.strip())
    if not out:
        raise ValueError("no usable digest texts")
    return out


async def claude_summarize(
    items: list[NewsItem], settings: Settings
) -> list[Digest]:
    if AsyncAnthropic is None:
        raise RuntimeError("anthropic SDK not installed")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    max_msgs = max(1, int(settings.max_digest_messages or 3))
    user_prompt = _build_user_prompt(items, max_msgs)

    log.info(
        "claude: requesting digest (model=%s, items=%d, max_msgs=%d)",
        settings.anthropic_model,
        len(items),
        max_msgs,
    )
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1500,
        system=_CLAUDE_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Concatenate text blocks.
    parts: list[str] = []
    for block in resp.content or []:
        # block can be a TextBlock with .text or a dict.
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if isinstance(text, str):
            parts.append(text)
    raw = "".join(parts).strip()
    if not raw:
        raise RuntimeError("empty response from Claude")

    digest_texts = _parse_claude_json(raw)
    digest_texts = digest_texts[:max_msgs]

    images = _unique_image_urls(items)
    image_assignment = _assign_images(len(digest_texts), images)

    digests: list[Digest] = []
    for idx, raw_text in enumerate(digest_texts):
        img = image_assignment[idx]
        # Claude is asked for plain text, so escape it as HTML body.
        text = html.escape(raw_text)
        text = _enforce_budget(text, has_image=bool(img))
        digests.append(Digest(text=text, image_url=img))
    return digests


# --- Public entry point ----------------------------------------------------


async def make_digests(
    items: list[NewsItem], settings: Settings
) -> list[Digest]:
    """Return 0..max_digest_messages digests for *items*.

    Tries Claude first when ``ANTHROPIC_API_KEY`` is set; falls back to the
    local rule-based digest on any error.
    """
    if not items:
        return []

    if settings.anthropic_api_key and AsyncAnthropic is not None:
        try:
            digests = await claude_summarize(items, settings)
            if digests:
                return digests
            log.warning("claude returned no digests; falling back to local")
        except Exception as e:  # noqa: BLE001
            log.warning("claude summarization failed (%s); using local digest", e)

    return local_digest(items, settings)