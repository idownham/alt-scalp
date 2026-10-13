"""SQLite storage for recordings (data/recordings/, gitignored).

Everything the recorder needs to resume after a crash is in the database: which
games are scheduled, which markets were loaded, and whether each game's trades
have been fetched. Restarting the recorder just carries on.

Units: prices are integer 1/10,000 dollar (`_e4`), sizes integer 1/100 contract
(`_e2`), wall-clock times integer nanoseconds since the Unix epoch (`_ns`) or ISO-8601
UTC text. Raw API JSON is kept alongside parsed values for the evidence trail.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from altscalp.kalshi import Book, price_e4, size_e2
from altscalp.schedule import Game

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    event_ticker      TEXT PRIMARY KEY,
    league            TEXT NOT NULL,
    title             TEXT NOT NULL,
    start_utc         TEXT NOT NULL,   -- scheduled start (milestone start_date)
    window_start_utc  TEXT NOT NULL,
    window_end_utc    TEXT NOT NULL,
    home_team_id      TEXT,
    milestone_id      TEXT NOT NULL,
    first_seen_ns     INTEGER NOT NULL,
    markets_loaded_ns INTEGER,
    trades_fetched_ns INTEGER,
    trades_note       TEXT
);
CREATE TABLE IF NOT EXISTS schedule_changes (
    event_ticker  TEXT NOT NULL,
    old_start_utc TEXT NOT NULL,
    new_start_utc TEXT NOT NULL,
    seen_ns       INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS markets (
    ticker         TEXT PRIMARY KEY,
    event_ticker   TEXT NOT NULL REFERENCES games(event_ticker),
    is_home        INTEGER,            -- 1 home team wins, 0 away, NULL unknown
    fee_type       TEXT,
    fee_multiplier TEXT,
    price_ranges   TEXT,               -- JSON, the market's valid price grid
    raw            TEXT NOT NULL,      -- market JSON when loaded
    loaded_ns      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS incentives (
    ticker     TEXT NOT NULL,
    program_id TEXT NOT NULL,
    raw        TEXT NOT NULL,
    seen_ns    INTEGER NOT NULL,
    PRIMARY KEY (ticker, program_id)
);
CREATE TABLE IF NOT EXISTS polls (
    id          INTEGER PRIMARY KEY,
    t_sent_ns   INTEGER NOT NULL,
    t_recv_ns   INTEGER NOT NULL,
    n_tickers   INTEGER NOT NULL,
    ok          INTEGER NOT NULL,
    error       TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY,
    poll_id     INTEGER NOT NULL REFERENCES polls(id),
    ticker      TEXT NOT NULL,
    t_sent_ns   INTEGER NOT NULL,
    t_recv_ns   INTEGER NOT NULL,
    yes_bid_e4  INTEGER,               -- best YES bid
    yes_ask_e4  INTEGER,               -- 1 - best NO bid
    book        TEXT NOT NULL          -- orderbook_fp JSON as received (all levels)
);
CREATE INDEX IF NOT EXISTS snapshots_ticker_time ON snapshots(ticker, t_recv_ns);
CREATE TABLE IF NOT EXISTS trades (
    trade_id           TEXT PRIMARY KEY,
    ticker             TEXT NOT NULL,
    created_time       TEXT NOT NULL,
    yes_price_e4       INTEGER NOT NULL,
    count_e2           INTEGER NOT NULL,
    taker_outcome_side TEXT,
    taker_book_side    TEXT,
    is_block_trade     INTEGER,
    raw                TEXT NOT NULL,
    fetched_ns         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS trades_ticker_time ON trades(ticker, created_time);
CREATE TABLE IF NOT EXISTS log (
    id      INTEGER PRIMARY KEY,
    t_ns    INTEGER NOT NULL,
    kind    TEXT NOT NULL,             -- start, stop, poll_error, refresh_error, schedule_change, ...
    message TEXT NOT NULL
);
"""


def iso(dt: datetime) -> str:
    """Fixed-width UTC text, so string comparison in SQL is time comparison."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def log(self, t_ns: int, kind: str, message: str) -> None:
        with self.db:
            self.db.execute("INSERT INTO log (t_ns, kind, message) VALUES (?, ?, ?)", (t_ns, kind, message))

    # --- schedule ---------------------------------------------------------

    def upsert_game(self, game: Game, now_ns: int) -> str | None:
        """Insert or update a game. Returns the old start if the scheduled start changed."""
        row = self.db.execute("SELECT start_utc FROM games WHERE event_ticker = ?", (game.event_ticker,)).fetchone()
        new_start = iso(game.start)
        with self.db:
            if row is None:
                self.db.execute(
                    "INSERT INTO games (event_ticker, league, title, start_utc, window_start_utc, window_end_utc,"
                    " home_team_id, milestone_id, first_seen_ns) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (game.event_ticker, game.league, game.title, new_start, iso(game.window_start),
                     iso(game.window_end), game.home_team_id, game.milestone_id, now_ns),
                )
                return None
            if row["start_utc"] == new_start:
                return None
            self.db.execute(
                "UPDATE games SET start_utc = ?, window_start_utc = ?, window_end_utc = ?, home_team_id = ?"
                " WHERE event_ticker = ?",
                (new_start, iso(game.window_start), iso(game.window_end), game.home_team_id, game.event_ticker),
            )
            self.db.execute(
                "INSERT INTO schedule_changes (event_ticker, old_start_utc, new_start_utc, seen_ns) VALUES (?, ?, ?, ?)",
                (game.event_ticker, row["start_utc"], new_start, now_ns),
            )
            return row["start_utc"]

    def games_needing_markets(self, before_utc: str, after_utc: str) -> list[sqlite3.Row]:
        """Games without markets loaded whose window starts before `before_utc` and ends after `after_utc`."""
        return self.db.execute(
            "SELECT * FROM games WHERE markets_loaded_ns IS NULL AND window_start_utc <= ? AND window_end_utc > ?",
            (before_utc, after_utc),
        ).fetchall()

    def save_markets(self, event_ticker: str, markets: Iterable[dict[str, Any]], now_ns: int) -> None:
        with self.db:
            for m in markets:
                self.db.execute(
                    "INSERT OR REPLACE INTO markets (ticker, event_ticker, is_home, fee_type, fee_multiplier,"
                    " price_ranges, raw, loaded_ns) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (m["ticker"], event_ticker, m.get("_is_home"), m.get("_fee_type"), m.get("_fee_multiplier"),
                     json.dumps(m.get("price_ranges")), json.dumps(m), now_ns),
                )
            self.db.execute("UPDATE games SET markets_loaded_ns = ? WHERE event_ticker = ?", (now_ns, event_ticker))

    def active_tickers(self, now_utc: str, home_only: bool = False) -> list[str]:
        sql = (
            "SELECT m.ticker FROM markets m JOIN games g USING (event_ticker)"
            " WHERE g.window_start_utc <= ? AND ? < g.window_end_utc"
        )
        if home_only:
            sql += " AND m.is_home = 1"
        return [r[0] for r in self.db.execute(sql + " ORDER BY m.ticker", (now_utc, now_utc))]

    def upcoming_tickers(self, until_utc: str, now_utc: str) -> list[str]:
        """Loaded markets whose game window overlaps [now, until)."""
        return [r[0] for r in self.db.execute(
            "SELECT m.ticker FROM markets m JOIN games g USING (event_ticker)"
            " WHERE g.window_start_utc < ? AND g.window_end_utc > ?", (until_utc, now_utc))]

    def next_window_start(self, now_utc: str) -> str | None:
        row = self.db.execute(
            "SELECT MIN(window_start_utc) FROM games WHERE window_start_utc > ?", (now_utc,)
        ).fetchone()
        return row[0]

    def save_incentive(self, ticker: str, program: dict[str, Any], now_ns: int) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO incentives (ticker, program_id, raw, seen_ns) VALUES (?, ?, ?, ?)",
                (ticker, program["id"], json.dumps(program), now_ns),
            )

    # --- polling ----------------------------------------------------------

    def save_poll(
        self, t_sent_ns: int, t_recv_ns: int, tickers: list[str], books: dict[str, Book] | None, error: str | None
    ) -> int:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO polls (t_sent_ns, t_recv_ns, n_tickers, ok, error) VALUES (?, ?, ?, ?, ?)",
                (t_sent_ns, t_recv_ns, len(tickers), int(books is not None), error),
            )
            poll_id = cur.lastrowid
            for book in (books or {}).values():
                self.db.execute(
                    "INSERT INTO snapshots (poll_id, ticker, t_sent_ns, t_recv_ns, yes_bid_e4, yes_ask_e4, book)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (poll_id, book.ticker, t_sent_ns, t_recv_ns, book.best_yes_bid_e4, book.best_yes_ask_e4,
                     json.dumps(book.raw, separators=(",", ":"))),
                )
        return poll_id

    # --- trades -----------------------------------------------------------

    def games_needing_trades(self, ended_before_utc: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM games WHERE trades_fetched_ns IS NULL AND window_end_utc <= ? ORDER BY window_end_utc",
            (ended_before_utc,),
        ).fetchall()

    def game_tickers(self, event_ticker: str) -> list[str]:
        return [r[0] for r in self.db.execute(
            "SELECT ticker FROM markets WHERE event_ticker = ? ORDER BY ticker", (event_ticker,))]

    def snapshot_count(self, tickers: list[str]) -> int:
        if not tickers:
            return 0
        marks = ",".join("?" * len(tickers))
        return self.db.execute(f"SELECT COUNT(*) FROM snapshots WHERE ticker IN ({marks})", tickers).fetchone()[0]

    def save_trades(self, trades: Iterable[dict[str, Any]], now_ns: int) -> int:
        """Insert trades, ignoring ones already stored (deduplicated by trade_id). Returns rows added."""
        added = 0
        with self.db:
            for t in trades:
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO trades (trade_id, ticker, created_time, yes_price_e4, count_e2,"
                    " taker_outcome_side, taker_book_side, is_block_trade, raw, fetched_ns)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (t["trade_id"], t["ticker"], t["created_time"], price_e4(t["yes_price_dollars"]),
                     size_e2(t["count_fp"]), t.get("taker_outcome_side"), t.get("taker_book_side"),
                     None if t.get("is_block_trade") is None else int(t["is_block_trade"]), json.dumps(t), now_ns),
                )
                added += cur.rowcount
        return added

    def mark_trades_fetched(self, event_ticker: str, now_ns: int, note: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE games SET trades_fetched_ns = ?, trades_note = ? WHERE event_ticker = ?",
                (now_ns, note, event_ticker),
            )
