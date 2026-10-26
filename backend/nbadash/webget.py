"""One place for fetching NBA-hosted static files (injury PDFs, lineup JSON, index pages).

curl_cffi with a browser TLS fingerprint, like the rest of the project: some NBA hosts (cdn.nba.com) refuse plain clients,
and using it everywhere keeps behaviour the same if the others start to.
"""
from __future__ import annotations

from typing import Optional

HEADERS = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com"}


class FetchError(Exception):
    """Network failure or an unexpected HTTP status."""


def fetch(url: str, *, timeout: float = 30.0, missing_ok: bool = True) -> Optional[bytes]:
    """Body of `url`, or None when the server says it doesn't exist (404/403 on these static hosts) and missing_ok."""
    from curl_cffi import requests as cffi
    try:
        r = cffi.get(url, impersonate="chrome", timeout=timeout, headers=HEADERS)
    except Exception as e:
        raise FetchError(f"{url}: {type(e).__name__}: {e}") from e
    if r.status_code == 200:
        return r.content
    if missing_ok and r.status_code in (403, 404):
        return None
    raise FetchError(f"{url}: HTTP {r.status_code}")
