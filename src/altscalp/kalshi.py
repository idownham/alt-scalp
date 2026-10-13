"""Read-only Kalshi client for the public market-data endpoints the recorder needs.

Adapted from alt-arb `src/altarb/venues/kalshi.py` @ 594878f. It holds no credentials
and has no order-placement code (CLAUDE.md rule 1).

Units: Kalshi sends prices as dollar strings with up to 4 decimals ("0.5100") and
contract counts as fixed-point strings with 2 decimals ("102.94"). They are converted
exactly to integers: prices in 1/10,000 dollar ("e4"), sizes in 1/100 contract ("e2").
Never float (CLAUDE.md rule 5).

Order books contain bids only. The YES ask is 1 - best NO bid. The API has been
seen returning levels worst-to-best even though the docs say best-to-worst, so
levels are always sorted here, best (highest) first.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from altscalp.http import RateLimitCounter, get_json

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
MAX_ORDERBOOK_TICKERS = 100  # GET /markets/orderbooks limit


def price_e4(value: str) -> int:
    """'0.5100' -> 5100. Raises if the string has more precision than 1/10,000."""
    return _exact_int(Decimal(value) * 10_000, value)


def size_e2(value: str) -> int:
    """'102.94' -> 10294. Raises if the string has more precision than 1/100."""
    return _exact_int(Decimal(value) * 100, value)


def _exact_int(scaled: Decimal, original: str) -> int:
    if scaled != scaled.to_integral_value():
        raise ValueError(f"unexpected precision in {original!r}")
    return int(scaled)


@dataclass(frozen=True)
class Level:
    price_e4: int
    size_e2: int


@dataclass(frozen=True)
class Book:
    ticker: str
    yes_bids: list[Level]  # best (highest) first
    no_bids: list[Level]  # best (highest) first
    raw: dict[str, Any]  # the API's orderbook_fp object, as received

    @property
    def best_yes_bid_e4(self) -> int | None:
        return self.yes_bids[0].price_e4 if self.yes_bids else None

    @property
    def best_yes_ask_e4(self) -> int | None:
        return 10_000 - self.no_bids[0].price_e4 if self.no_bids else None


def parse_book(ticker: str, orderbook_fp: dict[str, Any]) -> Book:
    return Book(
        ticker=ticker,
        yes_bids=_parse_levels(orderbook_fp.get("yes_dollars")),
        no_bids=_parse_levels(orderbook_fp.get("no_dollars")),
        raw=orderbook_fp,
    )


def _parse_levels(raw: list[list[str]] | None) -> list[Level]:
    levels = [Level(price_e4(price), size_e2(size)) for price, size in raw or []]
    return sorted(levels, key=lambda lvl: lvl.price_e4, reverse=True)


class KalshiClient:
    """Public market-data client. Holds no credentials and cannot place orders."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 10.0,
        http: httpx.Client | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http or httpx.Client(base_url=base_url, timeout=timeout)
        self._max_retries = max_retries
        self._sleep = sleep
        self.rate_limits = RateLimitCounter()

    def __enter__(self) -> KalshiClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def milestones(self, competition: str, minimum_start_date: str) -> Iterator[dict[str, Any]]:
        """Game milestones (scheduled start = `start_date`) for one league, e.g. 'NFL'."""
        params = {"competition": competition, "minimum_start_date": minimum_start_date, "limit": 200}
        yield from self._paginate("/milestones", params, "milestones")

    def event_markets(self, event_ticker: str) -> list[dict[str, Any]]:
        return list(self._paginate("/markets", {"event_ticker": event_ticker, "limit": 100}, "markets"))

    def series(self, series_ticker: str) -> dict[str, Any]:
        return self._get(f"/series/{series_ticker}")["series"]

    def active_incentive_programs(self) -> Iterator[dict[str, Any]]:
        params = {"status": "active", "limit": 1000}
        yield from self._paginate("/incentive_programs", params, "incentive_programs", cursor_key="next_cursor")

    def orderbooks(self, tickers: Iterable[str], max_retries: int = 0) -> dict[str, Book]:
        """Full-depth books for up to 100 tickers in one request.

        Retries default to 0: the recorder polls every few seconds, so the next tick
        is the retry, and blocking on backoff would only widen the gap.
        """
        tickers = list(tickers)
        if not 1 <= len(tickers) <= MAX_ORDERBOOK_TICKERS:
            raise ValueError(f"need 1..{MAX_ORDERBOOK_TICKERS} tickers, got {len(tickers)}")
        params = [("tickers", t) for t in tickers]
        data = get_json(self._http, "/markets/orderbooks", params, max_retries, self._sleep, self.rate_limits)
        return {ob["ticker"]: parse_book(ob["ticker"], ob["orderbook_fp"]) for ob in data.get("orderbooks", [])}

    def trades(self, ticker: str, min_ts: int, max_ts: int) -> Iterator[dict[str, Any]]:
        """Public trade tape for one market between two Unix timestamps (seconds)."""
        params = {"ticker": ticker, "min_ts": min_ts, "max_ts": max_ts, "limit": 1000}
        yield from self._paginate("/markets/trades", params, "trades")

    def _paginate(
        self, path: str, params: dict[str, Any], key: str, cursor_key: str = "cursor"
    ) -> Iterator[dict[str, Any]]:
        params = dict(params)
        while True:
            data = self._get(path, params)
            yield from data.get(key) or []
            cursor = data.get(cursor_key)
            if not cursor:
                return
            params["cursor"] = cursor

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return get_json(self._http, path, params, self._max_retries, self._sleep, self.rate_limits)
