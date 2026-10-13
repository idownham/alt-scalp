"""The S1 recorder: order-book snapshots around game start, then the trade tape.

Loop:
- Every `refresh_every` seconds: re-read the schedule (milestones, 3 requests),
  load markets for games starting within the hour, and note any liquidity
  incentive on those markets.
- Every `interval` seconds while any game's window is open: one
  GET /markets/orderbooks per 100 tickers, stored with send/receive timestamps.
- After a window closes: fetch that game's trades once, deduplicated by trade_id.
  The tape persists, so this works even hours later (e.g. after a crash).

Rate: a full slate is one book request per tick (~0.4 req/s) plus a few schedule
and trade requests, well under Basic's ~20 req/s (CLAUDE.md rule 6).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from altscalp.kalshi import MAX_ORDERBOOK_TICKERS, KalshiClient
from altscalp.schedule import LEAGUES, WINDOW_AFTER, League, game_from_milestone, is_home_market
from altscalp.store import Store, iso

log = logging.getLogger(__name__)

MARKET_LEAD = timedelta(hours=1)  # load markets this long before a window opens
TRADES_DELAY = timedelta(minutes=2)  # wait this long after a window closes before fetching trades
MAX_IDLE_SLEEP = 30.0
JUMP_THRESHOLD = 30.0  # a loop running this much longer than planned means the machine slept or stalled


class Recorder:
    def __init__(
        self,
        client: KalshiClient,
        store: Store,
        interval: float = 2.5,
        refresh_every: float = 600.0,
        home_only: bool = False,
        leagues: dict[str, League] = LEAGUES,
        clock: Callable[[], int] = time.time_ns,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.store = store
        self.interval = interval
        self.refresh_every = refresh_every
        self.home_only = home_only
        self.leagues = leagues
        self.clock = clock
        self.sleep = sleep
        self._next_refresh_ns = 0
        self._series_fees: dict[str, tuple[str, str]] = {}
        self._last_429 = 0

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.clock() / 1e9, tz=timezone.utc)

    # --- schedule ---------------------------------------------------------

    def refresh_schedule(self) -> None:
        now_ns, now = self.clock(), self.now()
        since = (now - WINDOW_AFTER - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._series_fees.clear()  # re-read fees each refresh so a mid-season change is captured
        seen = 0
        for league in self.leagues.values():
            for milestone in self.client.milestones(league.name, since):
                game = game_from_milestone(milestone, league)
                if game is None:
                    continue
                seen += 1
                old_start = self.store.upsert_game(game, now_ns)
                if old_start:
                    msg = f"{game.event_ticker} start moved {old_start} -> {iso(game.start)}"
                    log.warning(msg)
                    self.store.log(now_ns, "schedule_change", msg)
        log.info("schedule refreshed: %d games", seen)
        self.load_due_markets()
        self.check_incentives()

    def load_due_markets(self) -> None:
        now = self.now()
        for game in self.store.games_needing_markets(iso(now + MARKET_LEAD), iso(now)):
            league = self.leagues[game["league"]]
            fee_type, fee_multiplier = self._series_fee(league.series)
            markets = self.client.event_markets(game["event_ticker"])
            for m in markets:
                m["_is_home"] = _bool_to_int(is_home_market(m, game["home_team_id"]))
                m["_fee_type"], m["_fee_multiplier"] = fee_type, fee_multiplier
            self.store.save_markets(game["event_ticker"], markets, self.clock())
            homes = [m["ticker"] for m in markets if m["_is_home"] == 1]
            log.info("loaded %d markets for %s (home: %s)", len(markets), game["event_ticker"], homes or "unknown")
            if len(homes) != 1:
                self.store.log(self.clock(), "home_unknown", f"{game['event_ticker']}: home markets {homes}")

    def _series_fee(self, series: str) -> tuple[str, str]:
        if series not in self._series_fees:
            s = self.client.series(series)
            self._series_fees[series] = (s["fee_type"], str(s["fee_multiplier"]))
        return self._series_fees[series]

    def check_incentives(self) -> None:
        """Record any liquidity incentive on markets we're about to record (it makes a game not clean)."""
        now = self.now()
        tickers = set(self.store.upcoming_tickers(iso(now + MARKET_LEAD), iso(now)))
        if not tickers:
            return
        for program in self.client.active_incentive_programs():
            if program.get("market_ticker") in tickers:
                self.store.save_incentive(program["market_ticker"], program, self.clock())
                log.warning("incentive program active on %s", program["market_ticker"])

    # --- polling ----------------------------------------------------------

    def poll(self, tickers: list[str]) -> None:
        for i in range(0, len(tickers), MAX_ORDERBOOK_TICKERS):
            batch = tickers[i : i + MAX_ORDERBOOK_TICKERS]
            t_sent = self.clock()
            try:
                books = self.client.orderbooks(batch)
                error = None
                missing = set(batch) - set(books)
                if missing:
                    error = f"missing books: {sorted(missing)}"
            except Exception as exc:  # noqa: BLE001 - any failure is logged as a gap, never fatal
                books, error = None, f"{type(exc).__name__}: {exc}"
            t_recv = self.clock()
            self.store.save_poll(t_sent, t_recv, batch, books, error)
            if books is None:
                log.warning("poll failed (%d tickers): %s", len(batch), error)
                self.store.log(t_recv, "poll_error", error or "")
        if self.client.rate_limits.count != self._last_429:
            self.store.log(self.clock(), "rate_limited", f"429 total so far: {self.client.rate_limits.count}")
            self._last_429 = self.client.rate_limits.count

    # --- trades -----------------------------------------------------------

    def fetch_due_trades(self, limit: int = 1) -> None:
        """Fetch the trade tape for up to `limit` games whose window has closed."""
        now = self.now()
        for game in self.store.games_needing_trades(iso(now - TRADES_DELAY))[:limit]:
            tickers = self.store.game_tickers(game["event_ticker"])
            if self.store.snapshot_count(tickers) == 0:
                # Never recorded (e.g. laptop asleep). Its tape would be historical data, which is
                # out-of-sample only (docs/decisions.md), so don't fetch it.
                self.store.mark_trades_fetched(game["event_ticker"], self.clock(), "not recorded; skipped")
                continue
            lo = int(datetime.fromisoformat(game["window_start_utc"].replace("Z", "+00:00")).timestamp())
            hi = int(datetime.fromisoformat(game["window_end_utc"].replace("Z", "+00:00")).timestamp())
            added = sum(self.store.save_trades(self.client.trades(t, lo, hi), self.clock()) for t in tickers)
            self.store.mark_trades_fetched(game["event_ticker"], self.clock(), f"{added} trades")
            log.info("fetched %d trades for %s", added, game["event_ticker"])

    # --- main loop --------------------------------------------------------

    def step(self) -> float:
        """Do whatever is due now. Returns seconds to sleep before the next step."""
        tick_start = self.clock()
        if tick_start >= self._next_refresh_ns:
            try:
                self.refresh_schedule()
            except Exception as exc:  # noqa: BLE001
                log.exception("schedule refresh failed")
                self.store.log(self.clock(), "refresh_error", f"{type(exc).__name__}: {exc}")
            self._next_refresh_ns = tick_start + int(self.refresh_every * 1e9)

        now = self.now()
        tickers = self.store.active_tickers(iso(now), self.home_only)
        if not tickers and self.store.games_needing_markets(iso(now), iso(now)):
            # A window opened before its markets were loaded (e.g. just started up): load them now.
            try:
                self.load_due_markets()
            except Exception as exc:  # noqa: BLE001
                self.store.log(self.clock(), "refresh_error", f"{type(exc).__name__}: {exc}")
            tickers = self.store.active_tickers(iso(now), self.home_only)
        if tickers:
            self.poll(tickers)

        try:
            self.fetch_due_trades()
        except Exception as exc:  # noqa: BLE001
            log.exception("trade fetch failed")
            self.store.log(self.clock(), "trades_error", f"{type(exc).__name__}: {exc}")

        if tickers:
            elapsed = (self.clock() - tick_start) / 1e9
            return max(0.0, self.interval - elapsed)
        return self._idle_sleep()

    def _idle_sleep(self) -> float:
        now = self.now()
        wait = min(MAX_IDLE_SLEEP, max(0.0, (self._next_refresh_ns - self.clock()) / 1e9))
        nxt = self.store.next_window_start(iso(now))
        if nxt:
            until = (datetime.fromisoformat(nxt.replace("Z", "+00:00")) - now).total_seconds()
            wait = min(wait, max(0.0, until))
        return wait

    def run(self, stop: Callable[[], bool] = lambda: False) -> None:
        self.store.log(self.clock(), "start", f"interval={self.interval}s home_only={self.home_only}")
        try:
            while not stop():
                started = self.clock()
                wait = self.step()
                self.sleep(wait)
                self._check_jump(started, wait)
        finally:
            self.store.log(self.clock(), "stop", "recorder stopped")


    def _check_jump(self, started_ns: int, planned_wait_s: float) -> None:
        """Log when one loop took far longer than planned, so a gap's cause is on record."""
        took = (self.clock() - started_ns) / 1e9
        overrun = took - planned_wait_s
        if overrun > JUMP_THRESHOLD:
            msg = f"loop took {took:.0f}s, planned ~{planned_wait_s:.0f}s (machine asleep or network stalled)"
            log.warning(msg)
            self.store.log(self.clock(), "clock_jump", msg)


def _bool_to_int(value: bool | None) -> int | None:
    return None if value is None else int(value)
