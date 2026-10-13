from dataclasses import replace
from datetime import datetime, timedelta, timezone

from altscalp.schedule import LEAGUES, game_from_milestone
from altscalp.store import iso
from conftest import NHL_MARKETS, NHL_MILESTONE, START, TRADE


def _game():
    return game_from_milestone(NHL_MILESTONE, LEAGUES["NHL"])


def test_iso_is_fixed_width_so_text_order_is_time_order():
    a = datetime(2026, 10, 20, 1, 0, 0, tzinfo=timezone.utc)
    b = a + timedelta(microseconds=500_000)
    assert iso(a) < iso(b)
    assert len(iso(a)) == len(iso(b))


def test_schedule_change_is_recorded(store):
    assert store.upsert_game(_game(), 1) is None
    assert store.upsert_game(_game(), 2) is None  # unchanged
    moved = replace(_game(), start=START + timedelta(hours=1))
    assert store.upsert_game(moved, 3) == iso(START)
    row = store.db.execute("SELECT * FROM games").fetchone()
    assert row["start_utc"] == iso(START + timedelta(hours=1))
    assert row["window_start_utc"] == iso(START + timedelta(minutes=30))
    assert store.db.execute("SELECT COUNT(*) FROM schedule_changes").fetchone()[0] == 1


def _with_markets(store):
    store.upsert_game(_game(), 1)
    markets = [dict(m, _is_home=int(i == 0)) for i, m in enumerate(NHL_MARKETS)]
    store.save_markets("KXNHLGAME-26OCT19PITUTA", markets, 2)


def test_active_tickers_respect_window_bounds_and_home_only(store):
    _with_markets(store)
    before = iso(START - timedelta(minutes=30, seconds=1))
    opening = iso(START - timedelta(minutes=30))
    closing = iso(START + timedelta(minutes=20))
    assert store.active_tickers(before) == []
    assert len(store.active_tickers(opening)) == 2
    assert store.active_tickers(opening, home_only=True) == ["KXNHLGAME-26OCT19PITUTA-UTA"]
    assert store.active_tickers(closing) == []  # window is [start, end)


def test_trades_are_deduplicated(store):
    assert store.save_trades([TRADE], 1) == 1
    assert store.save_trades([TRADE, dict(TRADE, trade_id="other")], 2) == 1
    row = store.db.execute("SELECT * FROM trades WHERE trade_id = ?", (TRADE["trade_id"],)).fetchone()
    assert (row["yes_price_e4"], row["count_e2"], row["taker_book_side"]) == (5100, 947, "bid")
