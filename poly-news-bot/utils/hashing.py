"""URL canonicalization & hashing for stable news deduplication."""
from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query params that are tracking-only — strip before hashing.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = {
    "ref",
    "ref_src",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "_hsenc",
    "_hsmi",
    "cmpid",
    "cmp",
    "src",
}


def _is_tracking_param(key: str) -> bool:
    k = key.lower()
    if k in _TRACKING_PARAM_EXACT:
        return True
    return any(k.startswith(p) for p in _TRACKING_PARAM_PREFIXES)


def canonicalize_url(url: str) -> str:
    """Return a stable canonical representation of `url`.

    Rules:
      1. Lowercase scheme + host.
      2. Strip fragment.
      3. For Google News article redirect URLs, if there's a `url=` param, use it.
      4. Strip known tracking query parameters.
      5. Sort remaining query parameters alphabetically.
      6. Strip trailing slash from path (unless path is empty/root).
    """
    if not url:
        return url

    parts = urlsplit(url.strip())

    # Resolve Google News redirect: news.google.com/articles/?...&url=<real>
    host = parts.netloc.lower()
    if host.endswith("news.google.com"):
        qs = dict(parse_qsl(parts.query, keep_blank_values=True))
        target = qs.get("url")
        if target:
            return canonicalize_url(target)

    scheme = parts.scheme.lower() or "http"

    # Filter + sort query params
    pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(k)
    ]
    pairs.sort(key=lambda kv: (kv[0], kv[1]))
    query = urlencode(pairs, doseq=True)

    path = parts.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, host, path, query, ""))


def news_hash(url: str) -> str:
    """SHA256 hex digest of the canonicalized URL."""
    canon = canonicalize_url(url)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def fallback_hash(source: str, author: str | None, title: str, date_str: str) -> str:
    """Secondary hash when there's no stable URL (e.g. raw tweets)."""
    raw = f"{source}|{author or ''}|{title}|{date_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()