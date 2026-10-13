"""Shared fixtures: real API fragments (trimmed, captured 2026-10-13) and a fake Kalshi client."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from altscalp.http import RateLimitCounter
from altscalp.kalshi import parse_book
from altscalp.store import Store

# Trimmed from GET /milestones?competition=NHL (2026-10-13).
NHL_MILESTONE = {
    "id": "bbcde0e5-a1e3-4d5d-84f8-1a357114b3ad",
    "type": "hockey_match",
    "title": "Pittsburgh at Utah",
    "start_date": "2026-10-20T01:00:00Z",
    "primary_event_tickers": ["KXNHLGAME-26OCT19PITUTA"],
    "related_event_tickers": ["KXNHLGAME-26OCT19PITUTA"],
    "details": {
        "away_team_id": "1b5c6299-90f7-49c7-8617-264610d50488",
        "home_team_id": "7d20591d-c6fa-4b85-8d69-ff05fb3649ac",
        "league": "NHL",
        "main_game_event_ticker": "KXNHLGAME-26OCT19PITUTA",
        "status": "scheduled",
    },
}

# Trimmed from GET /markets?event_ticker=KXNHLGAME-26OCT19PITUTA (2026-10-13).
NHL_MARKETS = [
    {
        "ticker": "KXNHLGAME-26OCT19PITUTA-UTA",
        "event_ticker": "KXNHLGAME-26OCT19PITUTA",
        "custom_strike": {"hockey_team": "7d20591d-c6fa-4b85-8d69-ff05fb3649ac"},
        "price_ranges": [{"end": "1.0000", "start": "0.0000", "step": "0.0100"}],
        "occurrence_datetime": "2026-10-20T04:00:00Z",
        "status": "active",
    },
    {
        "ticker": "KXNHLGAME-26OCT19PITUTA-PIT",
        "event_ticker": "KXNHLGAME-26OCT19PITUTA",
        "custom_strike": {"hockey_team": "1b5c6299-90f7-49c7-8617-264610d50488"},
        "price_ranges": [{"end": "1.0000", "start": "0.0000", "step": "0.0100"}],
        "occurrence_datetime": "2026-10-20T04:00:00Z",
        "status": "active",
    },
]

# Real orderbook_fp levels (trimmed), in the API's own worst-to-best order.
BOOK_FP = {
    "no_dollars": [["0.0100", "30034.00"], ["0.3000", "102.94"], ["0.3800", "50.00"]],
    "yes_dollars": [["0.0100", "80920.00"], ["0.5000", "10.00"], ["0.5400", "50.00"]],
}

# From GET /markets/trades (2026-10-13).
TRADE = {
    "count_fp": "9.47",
    "created_time": "2026-10-13T00:09:56.589726Z",
    "is_block_trade": False,
    "no_price_dollars": "0.4900",
    "taker_book_side": "bid",
    "taker_outcome_side": "yes",
    "taker_side": "yes",
    "ticker": "KXNHLGAME-26OCT12VGKMIN-VGK",
    "trade_id": "0725fbd2-d081-84f4-1c04-e661ec3501b3",
    "yes_price_dollars": "0.5100",
}

SERIES = {"ticker": "KXNHLGAME", "fee_type": "quadratic_with_maker_fees", "fee_multiplier": 1}

START = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)


def ns(dt: datetime) -> int:
    return int(dt.timestamp()) * 1_000_000_000


class FakeClient:
    """Stands in for KalshiClient; records calls and serves canned data."""

    def __init__(self) -> None:
        self.milestones_by_league = {"NHL": [copy.deepcopy(NHL_MILESTONE)], "NFL": [], "NBA": []}
        self.markets = {"KXNHLGAME-26OCT19PITUTA": copy.deepcopy(NHL_MARKETS)}
        self.trades_by_ticker: dict[str, list[dict]] = {}
        self.incentives: list[dict] = []
        self.fail_orderbooks = False
        self.calls: list[tuple] = []
        self.rate_limits = RateLimitCounter()

    def milestones(self, competition, minimum_start_date):
        self.calls.append(("milestones", competition))
        return iter(copy.deepcopy(self.milestones_by_league.get(competition, [])))

    def event_markets(self, event_ticker):
        self.calls.append(("event_markets", event_ticker))
        return copy.deepcopy(self.markets[event_ticker])

    def series(self, series_ticker):
        self.calls.append(("series", series_ticker))
        return dict(SERIES, ticker=series_ticker)

    def active_incentive_programs(self):
        self.calls.append(("incentives",))
        return iter(self.incentives)

    def orderbooks(self, tickers):
        tickers = list(tickers)
        self.calls.append(("orderbooks", tuple(tickers)))
        if self.fail_orderbooks:
            raise RuntimeError("boom")
        return {t: parse_book(t, copy.deepcopy(BOOK_FP)) for t in tickers}

    def trades(self, ticker, min_ts, max_ts):
        self.calls.append(("trades", ticker, min_ts, max_ts))
        return iter(copy.deepcopy(self.trades_by_ticker.get(ticker, [])))

    def count(self, name: str) -> int:
        return sum(1 for c in self.calls if c[0] == name)


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t_ns = ns(t)

    def __call__(self) -> int:
        return self.t_ns

    def set(self, t: datetime) -> None:
        self.t_ns = ns(t)

    def advance(self, seconds: float) -> None:
        self.t_ns += int(seconds * 1e9)


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def client():
    return FakeClient()
