from datetime import timedelta

from altscalp.recorder import Recorder
from altscalp.report import coverage
from conftest import START, TRADE, Clock, FakeClient

HOME = "KXNHLGAME-26OCT19PITUTA-UTA"
AWAY = "KXNHLGAME-26OCT19PITUTA-PIT"


def _recorder(client, store, clock, **kw):
    return Recorder(client, store, clock=clock, sleep=lambda s: None, **kw)


def test_full_game_lifecycle(client, store):
    clock = Clock(START - timedelta(hours=3))
    rec = _recorder(client, store, clock)

    # Hours before: schedule known, markets not loaded yet, nothing polled, sleeps no longer than 30 s.
    wait = rec.step()
    assert client.count("milestones") == 3
    assert client.count("event_markets") == 0
    assert client.count("orderbooks") == 0
    assert 0 < wait <= 30

    # Within the hour before the window: markets loaded with home flag and fee type.
    clock.set(START - timedelta(minutes=80))
    rec._next_refresh_ns = 0
    rec.step()
    rows = {r["ticker"]: r for r in store.db.execute("SELECT * FROM markets")}
    assert rows[HOME]["is_home"] == 1 and rows[AWAY]["is_home"] == 0
    assert rows[HOME]["fee_type"] == "quadratic_with_maker_fees"
    assert client.count("orderbooks") == 0

    # Inside the window: one batched request per tick for both markets, then wait ~interval.
    clock.set(START - timedelta(minutes=30))
    wait = rec.step()
    assert client.calls[-1] == ("orderbooks", (AWAY, HOME))
    assert wait == 2.5
    snap = store.db.execute("SELECT * FROM snapshots WHERE ticker = ?", (HOME,)).fetchone()
    assert (snap["yes_bid_e4"], snap["yes_ask_e4"]) == (5400, 6200)

    # Window closed: no more polling; trades fetched once, 2 min later, over exactly the window.
    client.trades_by_ticker[HOME] = [TRADE]
    clock.set(START + timedelta(minutes=20))
    n = client.count("orderbooks")
    rec.step()
    assert client.count("orderbooks") == n
    assert client.count("trades") == 0
    clock.set(START + timedelta(minutes=23))
    rec.step()
    rec.step()
    trade_calls = [c for c in client.calls if c[0] == "trades"]
    assert len(trade_calls) == 2  # once per market, not repeated
    lo, hi = int((START - timedelta(minutes=30)).timestamp()), int((START + timedelta(minutes=20)).timestamp())
    assert all(c[2:] == (lo, hi) for c in trade_calls)
    assert store.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 1


def test_home_only_polls_one_market(client, store):
    clock = Clock(START - timedelta(minutes=30))
    _recorder(client, store, clock, home_only=True).step()
    assert client.calls[-1] == ("orderbooks", (HOME,))


def test_starting_mid_window_loads_markets_and_polls_immediately(client, store):
    clock = Clock(START)
    _recorder(client, store, clock).step()
    assert client.count("event_markets") == 1
    assert client.count("orderbooks") == 1


def test_poll_failure_is_logged_not_fatal(client, store):
    client.fail_orderbooks = True
    clock = Clock(START - timedelta(minutes=10))
    rec = _recorder(client, store, clock)
    rec.step()
    poll = store.db.execute("SELECT * FROM polls").fetchone()
    assert poll["ok"] == 0 and "boom" in poll["error"]
    assert store.db.execute("SELECT COUNT(*) FROM log WHERE kind = 'poll_error'").fetchone()[0] == 1
    client.fail_orderbooks = False
    rec.step()
    assert store.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2


def test_unrecorded_game_tape_is_not_fetched(client, store):
    # Recorder was off for the whole window: the tape would be historical data (out-of-sample only).
    rec = _recorder(client, store, Clock(START - timedelta(minutes=80)))
    rec.step()
    rec.clock = Clock(START + timedelta(hours=2))
    rec.step()
    assert client.count("trades") == 0
    note = store.db.execute("SELECT trades_note FROM games").fetchone()[0]
    assert note.startswith("not recorded")


def test_restart_resumes_from_database(client, store):
    clock = Clock(START - timedelta(minutes=5))
    _recorder(client, store, clock).step()
    # "Crash", then a new recorder on the same database after the window.
    client2 = FakeClient()
    clock.set(START + timedelta(minutes=30))
    _recorder(client2, store, clock).step()
    assert client2.count("event_markets") == 0  # markets already in the DB
    assert client2.count("trades") == 2
    assert store.db.execute("SELECT trades_note FROM games").fetchone()[0] == "0 trades"


def test_incentive_on_upcoming_market_is_recorded_and_makes_game_not_clean(client, store):
    client.incentives = [{"id": "p1", "market_ticker": HOME}, {"id": "p2", "market_ticker": "OTHER"}]
    clock = Clock(START - timedelta(minutes=30))
    rec = _recorder(client, store, clock)
    while clock.t_ns < Clock(START + timedelta(minutes=23)).t_ns:
        rec.step()
        clock.advance(2.5)
    assert [r[0] for r in store.db.execute("SELECT ticker FROM incentives")] == [HOME]
    [cov] = coverage(store)
    assert cov.incentive and not cov.clean


def test_clean_game_end_to_end(client, store):
    clock = Clock(START - timedelta(minutes=30))
    rec = _recorder(client, store, clock)
    while clock.t_ns < Clock(START + timedelta(minutes=23)).t_ns:
        rec.step()
        clock.advance(2.5)
    [cov] = coverage(store)
    assert cov.home_ticker == HOME
    assert cov.max_gap_s <= 2.5
    assert cov.clean


def test_gap_over_30s_makes_game_not_clean(client, store):
    clock = Clock(START - timedelta(minutes=30))
    rec = _recorder(client, store, clock)
    while clock.t_ns < Clock(START + timedelta(minutes=23)).t_ns:
        rec.step()
        clock.advance(31 if clock.t_ns == Clock(START).t_ns else 2.5)
    [cov] = coverage(store)
    assert cov.max_gap_s > 30
    assert not cov.clean
