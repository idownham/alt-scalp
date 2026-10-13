"""GET JSON from Kalshi, backing off on rate limits.

Copied from alt-arb `src/altarb/venues/http.py` @ 594878f and adapted: Kalshi's 429s
carry no Retry-After header (docs.kalshi.com/getting_started/rate_limits), so this
always uses exponential backoff, and it counts 429s so the recorder can log them.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)


class RateLimitCounter:
    """Running count of 429 responses, for logging how close we run to the limit."""

    def __init__(self) -> None:
        self.count = 0


def get_json(
    http: httpx.Client,
    path: str,
    params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    max_retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    rate_limits: RateLimitCounter | None = None,
) -> dict[str, Any]:
    """GET `path` and return the JSON body.

    On 429 Too Many Requests, waits 1s, 2s, 4s, ... and retries up to `max_retries`
    times. Any other error status raises immediately.
    """
    for attempt in range(max_retries + 1):
        response = http.get(path, params=params)
        if response.status_code != 429:
            break
        if rate_limits is not None:
            rate_limits.count += 1
        if attempt == max_retries:
            break
        wait = float(2**attempt)
        log.warning("429 rate limited on %s; retrying in %.0fs", path, wait)
        sleep(wait)
    response.raise_for_status()
    return response.json()
