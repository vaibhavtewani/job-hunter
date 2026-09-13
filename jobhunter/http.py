"""Shared HTTP client with polite defaults, small retry budget, and secret redaction."""
from __future__ import annotations

import logging
import re
import time

import httpx

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "job-hunter/0.1 (personal job search)"
_RETRY_STATUS = {429, 500, 502, 503, 504}
_SECRET_PARAM = re.compile(r"((?:api_key|apikey|key|token|access_token)=)[^&\s'\"]+", re.IGNORECASE)


_TELEGRAM_TOKEN = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def redact(text: str) -> str:
    return _TELEGRAM_TOKEN.sub("bot***", _SECRET_PARAM.sub(r"\1***", text))


def make_client(user_agent: str = DEFAULT_USER_AGENT, timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=True,
    )


def request_json(client: httpx.Client, method: str, url: str, retries: int = 2, **kwargs):
    for attempt in range(retries + 1):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt >= retries:
                raise
        else:
            if response.status_code not in _RETRY_STATUS or attempt >= retries:
                response.raise_for_status()
                return response.json()
        delay = 2 * (2 ** attempt)
        log.debug("retrying %s %s in %ss", method, redact(url), delay)
        time.sleep(delay)
    raise RuntimeError("unreachable")
