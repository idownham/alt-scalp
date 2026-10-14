# alt-scalp (Project Coin Toss) — Spec

*Written 2026-10-13 from the planning chat. Owner: Ian Downham.*

## Hypothesis
In the window around game start, Kalshi's mid-price oscillates around a fair value that isn't really changing,
by more than the bid-ask spread plus maker fees. A maker who quotes both sides (e.g. bid 48¢ / ask 51¢) can
earn the spread from that noise without being picked off too often by informed traders.

## Why maker, not taker
Taking liquidity costs ~1.75¢/contract each way at a 50¢ price (Kalshi taker fee `0.07 × P × (1−P)`), so a
round trip costs ~3.5¢. A visible 2¢ wiggle doesn't cover that, and much of the wiggle seen in "last price" is
bid-ask bounce, not real movement. Makers pay much less (often 0.25× taker, or zero, depending on the series),
so if the edge exists it's on the maker side.

## The main risk: adverse selection
Resting orders get filled exactly when real information arrives — a late scratch, an injury report, a first-drive
turnover. Then the price keeps going instead of reverting, and the maker holds the wrong side. Every stage below
must measure this, not just gross spread captured.

## Scope (decided 2026-10-13)
| Decision | Choice |
|---|---|
| Venue | Kalshi only |
| Leagues | NFL, NBA (regular season only, starts Oct 20), NHL |
| Recorder host | Laptop to start; second server (~$6/mo) if missed windows become a problem |
| Sample | 20 clean games, ≥ 5 per league |
| Money | None. Read-only research. |

## Stages

### S0 — Research (venue mechanics)
Answer these before writing the recorder; record answers with sources in `docs/decisions.md` or a `docs/s0-research.md`:
- Maker vs taker fee type and multiplier for each of the three game series (`KXNFLGAME`, `KXNBAGAME`, `KXNHLGAME`),
  including any scheduled fee changes.
- Tick size, minimum order size, post-only order availability.
- **Public trade tape:** is there a public trades endpoint, how granular (timestamps, size, aggressor side), how far
  back? Without it, fills can't be simulated honestly — this is the most important question.
- Order book depth available from REST (how many levels).
- Rate limits for reads (Basic ≈ 20 req/s; confirm) and, for later, order placement/cancel limits.
- Liquidity incentive programs: Kalshi's volume incentive program ended 2026-10-13; check what liquidity/maker
  incentives exist now and whether these sports markets qualify.
- How to get each game's scheduled start time reliably from the API.

### S1 — Recorder
- Records each target game from **30 min before scheduled start to 20 min after** (scheduled start = milestone `start_date`).
- Every **2–3 seconds** per game: full order book snapshot (both sides, all available levels).
- Trades from the public tape for the same window, fetched once after the window closes (the tape persists;
  `docs/s0-research.md` finding 1), deduplicated by `trade_id`.
- Stores to SQLite under `data/recordings/` (gitignored). One row per snapshot / trade, with fetch timestamps.
- Runs many games concurrently (a full NFL Sunday slate) well under the rate limit.
- Keeps the Mac awake while recording (`caffeinate`), logs gaps, survives a crash/restart.
- Schedules itself from the day's game list so Ian doesn't have to start it per game.
- Test run first (Oct 15–16 NHL); those games don't count.

### S2 — Analysis (is there tradable noise?)
Per game and per league:
- Mid-price path vs bid/ask; separate genuine mid moves from bid-ask bounce.
- Spread size over the window; how it changes at kickoff.
- Swing size distribution vs (spread + 2 × maker fee).
- Mean reversion: after a move of size X, how often and how fast does it come back?
- Jumps: identify large one-way moves and what caused them (kickoff, early score) — these are the adverse-selection events.

### S3 — Maker simulation
- Strategy: quote both sides at/inside the touch with fixed size, inventory cap, cancel/requote rules, and a
  "pull quotes" rule around known risk moments (e.g., right at kickoff).
- Fills: conservative — a resting order fills only when the tape shows trades through its price (assume last in queue).
- Output per game: fills, gross spread captured, fees, adverse-selection loss (price move against position after fill),
  net P&L, max inventory, max drawdown.

## Pre-registered criteria (CONFIRMED by Ian 2026-10-13 — see `decisions.md`; do not change without a dated entry there first)

**Definitions**
- **Window:** 30 min before to **20 min after** the scheduled start (milestone `start_date`).
- **Quoted market:** one market per game, the **home team's** market. Both may be recorded, but analysis and simulation use the home market only.
- **Maker fee at price P:** 0.0175 · P · (1 − P) per contract, at the actual price (not assumed 50¢).
- **Genuine mid move:** a change in mid-price whose new value persists ≥ 10 s.
- **Reversal:** a genuine mid move of ≥ X followed by a genuine move back of ≥ X within 5 min,
  where X = (spread + 2 × maker fee) at the time of the first move. A first move of ≥ 3 × X is a jump and doesn't
  count (`decisions.md` 2026-10-14). Exact mechanics are in `decisions.md`, "S2 implementation details".
- **Historical data:** out-of-sample only, untouched until S2 on recorded games is complete (`decisions.md`).

**Criteria**
- **Enough data:** ≥ 20 clean regular-season games, ≥ 5 per league. Clean = full window of book snapshots with no
  snapshot gap > 30 s (the trade tape is fetched after the window, so it isn't subject to the gap rule), and no
  postponement, trading pause, or active liquidity incentive on the quoted market.
- **S2 gate:** continue to S3 only if, in the median game, ≥ 3 reversals occur in the window. Otherwise stop: the
  noise isn't tradable.
- **S3 fill rule (decides GO/STOP):** a resting order fills only when the tape shows trades strictly through its price
  (last in queue). Sensitivity run, reported but not decisive: fill once volume traded at the order's price exceeds the
  queue ahead (from the last snapshot) plus the order's size.
- **S3 fees (decides GO/STOP):** each order's fee rounded up to the whole cent. The exact per-fill fee is reported as a sensitivity.
- **Adverse selection:** mark-out = mid-price move against the position **60 s** after each fill (primary); 10 s and 5 min are secondary, reported only.
- **S3 GO (worth considering live, tiny size):** total simulated net P&L after fees > 0 **and** positive in ≥ 60% of
  games (a game with 0 fills counts as not positive) **and** adverse-selection loss < 50% of gross spread captured
  **and** ≥ 100 simulated round trips in total. A bootstrap 90% CI on total net P&L is reported alongside but isn't a gate.
- **S3 STOP:** total net P&L ≤ 0, or adverse-selection loss ≥ gross spread captured.
- **In between:** MARGINAL — next cheapest test is a narrower window or fewer leagues, recorded in `decisions.md` before running.

## Timeline
| Dates | Step |
|---|---|
| Oct 14–15 | S0 research + build recorder |
| Oct 15–16 | Test run on NHL (doesn't count) |
| Oct 17–19 | Record NHL Sat/Sun, NFL Sun + Mon night |
| Oct 20–22 | Record NBA opening week |
| Oct 22–24 | S2 analysis |
| **Oct 25** | Class checkpoint — early prototype |
| Oct 26–Nov 8 | S3 maker simulation |
| **Nov 8** | Class checkpoint — working build + test |

Game-by-game progress: `docs/timeline.xlsx` → Game Tracker tab.

## Sources
- Kalshi API docs (rate limits): https://docs.kalshi.com/getting_started/rate_limits
- Kalshi fee schedule: https://kalshi.com/docs/kalshi-fee-schedule.pdf
- NBA 2026-27 start date: https://www.foxsports.com/stories/nba/when-does-2026-27-nba-season-start-opening-night-schedule
- Kalshi ending volume incentive program: https://www.gambling.com/us/news/kalshi-end-volume-incentive-program-october-13
- Kalshi liquidity incentives: https://fiftycentdollars.substack.com/p/kalshis-new-liquidity-incentives
