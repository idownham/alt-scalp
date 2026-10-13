"""Recording coverage per game, for the Game Tracker and the 'clean game' rule.

Clean (docs/spec.md, pre-registered): the quoted (home) market has book snapshots
covering the whole window with no gap > 30 s, and no postponement, trading
pause, or active liquidity incentive. Postponements and pauses can't be fully
detected here: schedule changes are flagged, and pauses must be checked by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from altscalp.store import Store

MAX_GAP_S = 30.0


@dataclass(frozen=True)
class Coverage:
    event_ticker: str
    league: str
    title: str
    start_utc: str
    home_ticker: str | None
    snapshots: int
    max_gap_s: float | None  # includes window start -> first and last -> window end
    trades: int
    trades_note: str | None
    incentive: bool
    schedule_changed: bool

    @property
    def clean(self) -> bool:
        return (
            self.home_ticker is not None
            and self.max_gap_s is not None
            and self.max_gap_s <= MAX_GAP_S
            and self.trades_note is not None
            and not self.incentive
            and not self.schedule_changed
        )


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _ns(iso_text: str) -> int:
    dt = datetime.fromisoformat(iso_text.replace("Z", "+00:00"))
    return (dt - EPOCH) // timedelta(microseconds=1) * 1000


def max_gap_seconds(times_ns: list[int], window_start_ns: int, window_end_ns: int) -> float | None:
    inside = sorted(t for t in times_ns if window_start_ns <= t <= window_end_ns)
    if not inside:
        return None
    points = [window_start_ns, *inside, window_end_ns]
    return max(b - a for a, b in zip(points, points[1:])) / 1e9


def coverage(store: Store, ended_before_utc: str | None = None) -> list[Coverage]:
    """Coverage for every game that has markets loaded (optionally only windows ended before a time)."""
    sql = "SELECT * FROM games WHERE markets_loaded_ns IS NOT NULL"
    args: tuple = ()
    if ended_before_utc:
        sql += " AND window_end_utc <= ?"
        args = (ended_before_utc,)
    out = []
    for g in store.db.execute(sql + " ORDER BY start_utc", args).fetchall():
        homes = [r[0] for r in store.db.execute(
            "SELECT ticker FROM markets WHERE event_ticker = ? AND is_home = 1", (g["event_ticker"],))]
        home = homes[0] if len(homes) == 1 else None
        times = [r[0] for r in store.db.execute(
            "SELECT t_recv_ns FROM snapshots WHERE ticker = ?", (home,))] if home else []
        trades = store.db.execute(
            "SELECT COUNT(*) FROM trades t JOIN markets m USING (ticker) WHERE m.event_ticker = ?",
            (g["event_ticker"],)).fetchone()[0]
        incentive = store.db.execute(
            "SELECT COUNT(*) FROM incentives i JOIN markets m USING (ticker) WHERE m.event_ticker = ?",
            (g["event_ticker"],)).fetchone()[0] > 0
        changed = store.db.execute(
            "SELECT COUNT(*) FROM schedule_changes WHERE event_ticker = ?", (g["event_ticker"],)).fetchone()[0] > 0
        out.append(Coverage(
            event_ticker=g["event_ticker"], league=g["league"], title=g["title"], start_utc=g["start_utc"],
            home_ticker=home, snapshots=len(times),
            max_gap_s=max_gap_seconds(times, _ns(g["window_start_utc"]), _ns(g["window_end_utc"])),
            trades=trades, trades_note=g["trades_fetched_ns"] and g["trades_note"],
            incentive=incentive, schedule_changed=changed,
        ))
    return out


def format_table(rows: list[Coverage]) -> str:
    lines = [f"{'start (UTC)':<17} {'lg':<3} {'event':<28} {'snaps':>6} {'maxgap':>7} {'trades':>6}  flags"]
    for c in rows:
        flags = []
        if c.home_ticker is None:
            flags.append("home?")
        if c.incentive:
            flags.append("incentive")
        if c.schedule_changed:
            flags.append("rescheduled")
        if c.trades_note is None:
            flags.append("trades-pending")
        gap = "-" if c.max_gap_s is None else f"{c.max_gap_s:.1f}s"
        flags.insert(0, "CLEAN" if c.clean else "not-clean")
        lines.append(
            f"{c.start_utc[:16]:<17} {c.league:<3} {c.event_ticker:<28} {c.snapshots:>6} {gap:>7} {c.trades:>6}  "
            + " ".join(flags)
        )
    return "\n".join(lines)
