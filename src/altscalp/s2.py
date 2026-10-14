"""S2 analysis: is there tradable noise around game start?

Per game, on the home team's market only (pre-registered, docs/spec.md):
- the mid path, split into genuine levels (persisting ≥ 10 s) vs flicker/bid-ask bounce;
- spread before and after the scheduled start;
- zigzag swings vs X = spread + 2 × maker fee, and reversals (≥ X out, ≥ X back within 5 min);
- jumps (genuine moves ≥ 3 × X), listed for manual cause-tagging.

The mechanics follow docs/decisions.md, "2026-10-14 — S2 implementation details". Prices are
integer 1/10,000 dollar (e4); mids and thresholds are exact Decimals.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from altscalp.fees import maker_coefficient, maker_fee_e4
from altscalp.report import coverage, ns_from_iso
from altscalp.store import Store

PERSIST_NS = 10 * 10**9  # genuine level: mid persists ≥ 10 s
BACK_WITHIN_NS = 300 * 10**9  # reversal: comes back within 5 min
JUMP_MULTIPLE = 3  # jump: a genuine move ≥ 3 × X
REVERSAL_GATE = 3  # S2 gate: ≥ 3 reversals in the median game
COUNTED_FROM_UTC = "2026-10-17T05:00:00.000000Z"  # Oct 17 00:00 CT


@dataclass(frozen=True)
class Quote:
    t_ns: int
    bid_e4: int
    ask_e4: int

    @property
    def mid_e4(self) -> Decimal:
        return Decimal(self.bid_e4 + self.ask_e4) / 2

    @property
    def spread_e4(self) -> int:
        return self.ask_e4 - self.bid_e4


@dataclass(frozen=True)
class Level:
    """A genuine mid level: held for at least PERSIST_NS."""

    t_ns: int  # when this mid first appeared
    mid_e4: Decimal
    spread_e4: int  # spread on the level's first snapshot


@dataclass(frozen=True)
class Reversal:
    pivot_t_ns: int
    extreme_t_ns: int
    back_t_ns: int
    x_e4: Decimal
    out_e4: Decimal  # size of the out leg (pivot -> extreme)

    @property
    def back_after_s(self) -> float:
        return (self.back_t_ns - self.extreme_t_ns) / 1e9


@dataclass
class Zigzag:
    legs: list[tuple[Decimal, Decimal]] = field(default_factory=list)  # completed out legs: (size, X at pivot)
    reversals: list[Reversal] = field(default_factory=list)


def genuine_levels(quotes: Sequence[Quote], persist_ns: int = PERSIST_NS) -> list[Level]:
    """Runs of constant mid lasting ≥ persist_ns, with consecutive equal levels merged."""
    runs: list[tuple[int, int, Quote]] = []  # (start, end, first quote)
    for q in quotes:
        if runs and runs[-1][2].mid_e4 == q.mid_e4:
            continue
        if runs:
            start, _, first = runs[-1]
            runs[-1] = (start, q.t_ns, first)
        runs.append((q.t_ns, q.t_ns, q))
    if runs and quotes:
        start, _, first = runs[-1]
        runs[-1] = (start, quotes[-1].t_ns, first)

    levels: list[Level] = []
    for start, end, first in runs:
        if end - start < persist_ns:
            continue
        if levels and levels[-1].mid_e4 == first.mid_e4:
            continue  # the flicker between them was dropped; same level continues
        levels.append(Level(start, first.mid_e4, first.spread_e4))
    return levels


def zigzag(
    levels: Sequence[Level], x_of: Callable[[Level], Decimal], back_within_ns: int = BACK_WITHIN_NS
) -> Zigzag:
    """Count reversals: ≥ X out from a pivot, then ≥ X back from the extreme within back_within_ns.

    While no out leg is under way, the pivot is the running low (for an up leg) or high (for a down
    leg) since the last turn, so a swing is caught wherever it starts.
    """
    out = Zigzag()
    if not levels:
        return out
    direction = 0  # +1 up, -1 down, 0 = no out leg under way
    low = high = pivot = extreme = levels[0]
    x = x_of(pivot)
    for lvl in levels[1:]:
        if direction == 0:
            if lvl.mid_e4 - low.mid_e4 >= x_of(low):
                direction, pivot, extreme = 1, low, lvl
            elif high.mid_e4 - lvl.mid_e4 >= x_of(high):
                direction, pivot, extreme = -1, high, lvl
            else:
                low = lvl if lvl.mid_e4 < low.mid_e4 else low
                high = lvl if lvl.mid_e4 > high.mid_e4 else high
                continue
            x = x_of(pivot)
            continue
        if (lvl.mid_e4 - extreme.mid_e4) * direction > 0:
            extreme = lvl  # out leg extends
            continue
        if (extreme.mid_e4 - lvl.mid_e4) * direction < x:
            continue
        size = abs(extreme.mid_e4 - pivot.mid_e4)
        out.legs.append((size, x))
        if lvl.t_ns - extreme.t_ns <= back_within_ns:
            out.reversals.append(Reversal(pivot.t_ns, extreme.t_ns, lvl.t_ns, x, size))
        # The extreme is the new pivot; the back leg is the next potential out leg.
        pivot = extreme
        x = x_of(pivot)
        if abs(lvl.mid_e4 - pivot.mid_e4) >= x:
            direction, extreme = -direction, lvl
        else:
            direction = 0
            low, high = (lvl, pivot) if lvl.mid_e4 < pivot.mid_e4 else (pivot, lvl)
    return out


def mid_at(quotes: Sequence[Quote], t_ns: int) -> Decimal | None:
    """Mid of the latest quote at or before t_ns (quotes sorted by time)."""
    lo, hi = 0, len(quotes)
    while lo < hi:
        mid = (lo + hi) // 2
        if quotes[mid].t_ns <= t_ns:
            lo = mid + 1
        else:
            hi = mid
    return quotes[lo - 1].mid_e4 if lo else None


def bounce_share(quotes: Sequence[Quote], trades: Sequence[tuple[int, int]]) -> tuple[int, int]:
    """(trade-price changes, of which with an unchanged mid). Trades are (t_ns, yes_price_e4), time-sorted."""
    changes = bounces = 0
    for (t0, p0), (t1, p1) in zip(trades, trades[1:]):
        if p0 == p1:
            continue
        changes += 1
        m0, m1 = mid_at(quotes, t0), mid_at(quotes, t1)
        if m0 is not None and m0 == m1:
            bounces += 1
    return changes, bounces


@dataclass
class GameResult:
    event_ticker: str
    league: str
    start_utc: str
    ticker: str
    counted: bool
    quotes: int
    raw_mid_changes: int
    genuine_moves: int
    spread_pre_median_e4: float | None
    spread_post_median_e4: float | None
    x_median_e4: Decimal | None
    trades: int
    trade_price_changes: int
    bounce_changes: int
    legs: list[tuple[Decimal, Decimal]]
    reversals: list[Reversal]
    jumps: list[tuple[float, Decimal, Decimal]]  # (seconds from scheduled start, size, X)

    @property
    def out_legs(self) -> int:
        return len(self.legs)

    @property
    def median_back_s(self) -> float | None:
        return statistics.median(r.back_after_s for r in self.reversals) if self.reversals else None


def analyze_game(store: Store, event_ticker: str) -> GameResult | None:
    g = store.db.execute("SELECT * FROM games WHERE event_ticker = ?", (event_ticker,)).fetchone()
    m = store.db.execute(
        "SELECT * FROM markets WHERE event_ticker = ? AND is_home = 1", (event_ticker,)
    ).fetchall()
    if g is None or len(m) != 1:
        return None
    m = m[0]
    lo, hi, start = ns_from_iso(g["window_start_utc"]), ns_from_iso(g["window_end_utc"]), ns_from_iso(g["start_utc"])
    quotes = [
        Quote(t, b, a)
        for t, b, a in store.db.execute(
            "SELECT t_recv_ns, yes_bid_e4, yes_ask_e4 FROM snapshots WHERE ticker = ? AND t_recv_ns BETWEEN ? AND ?"
            " AND yes_bid_e4 IS NOT NULL AND yes_ask_e4 IS NOT NULL ORDER BY t_recv_ns",
            (m["ticker"], lo, hi),
        )
    ]
    trades = [
        (ns_from_iso(ct), p)
        for ct, p in store.db.execute(
            "SELECT created_time, yes_price_e4 FROM trades WHERE ticker = ? ORDER BY created_time", (m["ticker"],)
        )
    ]
    trades = [(t, p) for t, p in trades if lo <= t <= hi]

    coeff = maker_coefficient(m["fee_type"], m["fee_multiplier"])

    def x_of(level: Level) -> Decimal:
        return Decimal(level.spread_e4) + 2 * maker_fee_e4(level.mid_e4, coeff)

    levels = genuine_levels(quotes)
    zz = zigzag(levels, x_of)
    jumps = []
    for a, b in zip(levels, levels[1:]):
        x = x_of(a)
        if abs(b.mid_e4 - a.mid_e4) >= JUMP_MULTIPLE * x:
            jumps.append(((b.t_ns - start) / 1e9, b.mid_e4 - a.mid_e4, x))
    raw_changes = sum(1 for a, b in zip(quotes, quotes[1:]) if a.mid_e4 != b.mid_e4)
    pre = [q.spread_e4 for q in quotes if q.t_ns < start]
    post = [q.spread_e4 for q in quotes if q.t_ns >= start]
    changes, bounces = bounce_share(quotes, trades)
    return GameResult(
        event_ticker=event_ticker,
        league=g["league"],
        start_utc=g["start_utc"],
        ticker=m["ticker"],
        counted=g["start_utc"] >= COUNTED_FROM_UTC,
        quotes=len(quotes),
        raw_mid_changes=raw_changes,
        genuine_moves=max(0, len(levels) - 1),
        spread_pre_median_e4=statistics.median(pre) if pre else None,
        spread_post_median_e4=statistics.median(post) if post else None,
        x_median_e4=statistics.median(x_of(lvl) for lvl in levels) if levels else None,
        trades=len(trades),
        trade_price_changes=changes,
        bounce_changes=bounces,
        legs=zz.legs,
        reversals=zz.reversals,
        jumps=jumps,
    )


@dataclass
class Gate:
    games: int
    per_league: dict[str, int]
    enough_data: bool
    median_reversals: float | None
    passed: bool | None  # None when there are no games


def evaluate_gate(results: Sequence[GameResult]) -> Gate:
    per_league: dict[str, int] = {}
    for r in results:
        per_league[r.league] = per_league.get(r.league, 0) + 1
    enough = len(results) >= 20 and all(per_league.get(lg, 0) >= 5 for lg in ("NFL", "NBA", "NHL"))
    if not results:
        return Gate(0, per_league, False, None, None)
    med = statistics.median(len(r.reversals) for r in results)
    return Gate(len(results), per_league, enough, med, med >= REVERSAL_GATE)


def clean_games(store: Store, now_utc: str, include_test: bool) -> list[str]:
    return [
        c.event_ticker
        for c in coverage(store, now_utc)
        if c.verdict(now_utc) == "CLEAN" and (include_test or c.start_utc >= COUNTED_FROM_UTC)
    ]


def format_results(results: Sequence[GameResult], gate: Gate, include_test: bool) -> str:
    c = lambda e4: "-" if e4 is None else f"{Decimal(e4) / 100:.2f}"  # noqa: E731 - e4 -> cents
    lines = [
        f"{'start (UTC)':<17} {'lg':<3} {'home market':<30} {'sprd pre/post¢':>14} {'X¢':>5} "
        f"{'mid chg':>7} {'genuine':>7} {'bounce':>9} {'legs':>4} {'rev':>3} {'back s':>6} {'jumps':>5}"
    ]
    for r in results:
        bounce = f"{r.bounce_changes}/{r.trade_price_changes}"
        back = "-" if r.median_back_s is None else f"{r.median_back_s:.0f}"
        lines.append(
            f"{r.start_utc[:16]:<17} {r.league:<3} {r.ticker:<30} "
            f"{c(r.spread_pre_median_e4) + '/' + c(r.spread_post_median_e4):>14} {c(r.x_median_e4):>5} "
            f"{r.raw_mid_changes:>7} {r.genuine_moves:>7} {bounce:>9} {r.out_legs:>4} {len(r.reversals):>3} "
            f"{back:>6} {len(r.jumps):>5}"
        )
    lines.append("")
    label = "TEST + counted games (test results don't count)" if include_test else "counted games"
    if gate.passed is None:
        lines.append(f"S2 gate: no {label} to evaluate yet.")
    else:
        lines.append(
            f"S2 gate over {gate.games} {label}: median reversals = {gate.median_reversals} "
            f"(need ≥ {REVERSAL_GATE}) -> {'PASS' if gate.passed else 'STOP'}"
        )
        leagues = ", ".join(f"{lg} {n}" for lg, n in sorted(gate.per_league.items()))
        lines.append(f"Sample: {leagues}; enough data (≥20, ≥5 per league): {'yes' if gate.enough_data else 'NO'}")
        if not gate.enough_data:
            lines.append("The gate isn't final until the sample is complete.")
    return "\n".join(lines)
