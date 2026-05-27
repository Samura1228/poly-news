"""Shared aiohttp session helpers with retries."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_USER_AGENT = "PolyNewsBot/1.0 (+https://t.me/your_bot)"


def build_session(
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> aiohttp.ClientSession:
    """Create an aiohttp ClientSession with realistic defaults."""
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    headers = {
        "User-Agent": user_agent,
        "Accept": (
            "application/rss+xml, application/atom+xml, application/xml, "
            "application/json, text/html, */*;q=0.5"
        ),
    }
    connector = aiohttp.TCPConnector(limit=50, ttl_dns_cache=300)
    return aiohttp.ClientSession(
        timeout=timeout, headers=headers, connector=connector
    )


async def fetch_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    *,
    attempts: int = 3,
    method: str = "GET",
    **kwargs: Any,
) -> aiohttp.ClientResponse:
    """Perform an HTTP request with exponential-backoff retries.

    Returns the response (already entered as a context). Caller is responsible
    for reading the body and closing the response (use `async with` at call site
    by passing returned response to it, OR call `.read()`/`.json()` then `.release()`).

    We deliberately do NOT use `async with` here so callers can read the body
    after a successful retry.
    """
    last_exc: Exception | None = None
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(
            (aiohttp.ClientError, aiohttp.ServerTimeoutError, TimeoutError)
        ),
        reraise=True,
    ):
        with attempt:
            try:
                resp = await session.request(method, url, **kwargs)
                # Treat 5xx as retryable
                if resp.status >= 500:
                    body_preview = await resp.text()
                    resp.release()
                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=resp.status,
                        message=f"server error {resp.status}: {body_preview[:200]}",
                    )
                return resp
            except Exception as e:
                last_exc = e
                raise
    # Unreachable, but to satisfy type checkers:
    raise last_exc if last_exc else RuntimeError("fetch_with_retry exhausted")


async def fetch_text(
    session: aiohttp.ClientSession, url: str, **kwargs: Any
) -> str:
    """Convenience: GET + return body text. Raises for non-2xx after retries."""
    resp = await fetch_with_retry(session, url, **kwargs)
    try:
        resp.raise_for_status()
        return await resp.text()
    finally:
        resp.release()


async def fetch_bytes(
    session: aiohttp.ClientSession, url: str, **kwargs: Any
) -> bytes:
    """Convenience: GET + return body bytes."""
    resp = await fetch_with_retry(session, url, **kwargs)
    try:
        resp.raise_for_status()
        return await resp.read()
    finally:
        resp.release()


async def fetch_json(
    session: aiohttp.ClientSession, url: str, **kwargs: Any
) -> Any:
    """Convenience: GET + return parsed JSON."""
    resp = await fetch_with_retry(session, url, **kwargs)
    try:
        resp.raise_for_status()
        return await resp.json(content_type=None)
    finally:
        resp.release()