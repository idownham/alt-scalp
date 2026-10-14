# Project Coin Toss — Journal & AI log

One entry per working session: date, work, evidence, observation, decision, AI use + Ian's judgment.

---

## 2026-10-13 — S0 research (venue mechanics)

**Work**
- Read `CLAUDE.md` and `docs/spec.md` and confirmed the plan summary with Claude.
- Answered every S0 question in the spec → [`docs/s0-research.md`](s0-research.md).
- No code written, no code copied from alt-arb, no API keys used.

**Sources / evidence**
- Kalshi API docs (docs.kalshi.com): rate limits, get-trades, orderbook, multi-orderbook, historical data, fee rounding,
  fixed-point, order direction, create-order V2, order groups, milestones.
- Live public API, unauthenticated read-only GETs (~60 requests): `/series/{KXNFLGAME,KXNBAGAME,KXNHLGAME}`,
  `/series/fee_changes`, `/markets`, `/events`, `/milestones`, `/markets/trades`, `/historical/trades`,
  `/historical/cutoff`, `/markets/{t}/orderbook`, `/markets/orderbooks`, candlesticks, `/incentive_programs`,
  `/account/endpoint_costs`.
- kalshi.com/fee-schedule (read in a browser; the fee-schedule PDF blocks automated download).
- Kalshi help center: Liquidity Incentive Program, Where to find them, Prop Combo legs program, Liquidity Provider Program.
- gambling.com / Legal Sports Report on the end of the Volume Incentive Program.

**Observations**
- A public trade tape exists, with timestamps, size and aggressor side. It persists after the game and can be
  backfilled → trades don't need live polling.
- Maker fee is 0.25× taker on all three series (0.0175·P·(1−P)); no fee changes are pending.
- No liquidity incentives on any game-winner market (active, upcoming, or since March 2026).
- Market `occurrence_datetime` is the expected end, not the start; the start comes from milestones.
- WebSockets need keys → the recorder uses REST polling.
- One liquid NHL game had a 1¢ spread (the minimum tick) at scheduled start.

**Decisions**
- Ian: historical data is out-of-sample only (option a).
- Ian: all other criteria suggestions accepted → criteria CONFIRMED in `spec.md`; window extended to +20 min.
  Both are logged in `decisions.md`.

**AI use + Ian's judgment**
- Claude (Opus 5.5, Claude Code) read the docs, ran the read-only API probes, and drafted `s0-research.md` and this
  entry. Every factual claim cites a doc page or a live API response from 2026-10-13.
- Limitations Claude flagged: the 0.07 base coefficient is inferred from the fee-schedule page's ranges, not quoted
  from the PDF; whether the multi-orderbook endpoint is billed per ticker is unknown; the trade-side skew is from one game only.
- *Ian's judgment:* historical data is out-of-sample only, option (a); all other criteria suggestions accepted →
  pre-registered criteria CONFIRMED in `spec.md` (`decisions.md`, 2026-10-13). Claude used the example values given in
  the suggestions as the concrete thresholds.

---

## 2026-10-13 — S1 recorder build

**Work**
- Built the recorder (`src/altscalp/`): `kalshi.py` (public read-only client), `http.py`, `schedule.py`,
  `store.py` (SQLite), `recorder.py` (main loop), `report.py` (coverage / clean check), `cli.py`
  (`altscalp record | status | schedule`).
- Copied and adapted from alt-arb @ 594878f (`venues/http.py`, `venues/kalshi.py`). The fee model was not copied
  yet; it isn't needed until S3. The recorder stores each series' `fee_type`/`fee_multiplier` alongside its markets.
- Tests: 33 unit tests plus 1 live test, all passing. Smoke test against the live API on NJ@DET: snapshots stored,
  home market detected correctly, ~150 ms per request, ~2 KB per book.
- Added a launchd agent for auto-restart. Ian approved installing it, and it was installed 2026-10-13 ~15:55 CT.
  Verified: after `kill -9` the agent restarted within the 30 s throttle and resumed from the database.

**Design choices (consistent with S0 findings and the confirmed criteria)**
- Schedule from milestones (`start_date`), not market times. NBA games before 2026-10-20 12:00Z are skipped as preseason.
- One `GET /markets/orderbooks` per tick for the whole slate (≤ 100 tickers). Both teams' markets are recorded;
  `--home-only` exists in case the multi-book call turns out to be billed per ticker.
- Trades are fetched once after each window. Games with zero snapshots get no trade fetch, because their tape would
  be historical data (out-of-sample only, per `decisions.md`).
- Window is −30/+20 min. A snapshot gap > 30 s, an incentive, or a schedule change makes `status` mark a game not clean.
- Prices are stored as integer 1/10,000 $, sizes as integer 1/100 contract, and the raw book JSON is kept.

**AI use + Ian's judgment**
- Claude wrote the code and tests and ran the smoke test. Known limits: trading pauses aren't detected automatically
  (check by hand); `caffeinate` can't keep a closed-lid laptop on battery awake.
- *Ian's judgment:* _(to fill in)_

**First test window (2026-10-13, NJ@DET, window 21:30–22:20Z) — not clean**
- Recorded normally from 21:30:00 to 21:38:24Z. Then the laptop lid was closed on battery (pmset log: 'Clamshell
  Sleep' at 21:38:22Z), and the Mac slept apart from brief maintenance wakes. Result: 222 snapshots instead of
  ~1,200, a max gap of 1,209 s, and 9 failed polls (DNS errors / timeouts during the wakes).
- The trade tape was still complete (1,641 trades fetched afterwards), which confirms the fetch-after-window design.
- The recorder code behaved correctly: it logged every failure and resumed on each wake. `caffeinate` cannot prevent
  lid-close sleep on battery.
- Follow-ups: the recorder now logs a `clock_jump` when a loop overruns by more than 30 s, so the cause of a gap is
  on record; `status` measures an open window's gap only up to now. Ian chose to move recording to an always-on
  server (the spec's fallback) before counted recording on Oct 17.

---

## 2026-10-14 — S2 analysis build

**Work**
- Wrote the open S2 mechanics into `decisions.md` as a **proposal** (mid, genuine level, X at the pivot, zigzag
  reversal rule, counted-from date, pooled median, jumps). This was committed (11d0dd7) *before* the code existed or
  ran on any data. One amendment followed before any run: the zigzag starts from the running high/low, so swings that
  begin with a drift aren't missed.
- Built `src/altscalp/s2.py` and `altscalp analyze`, plus `fees.py` (maker coefficient, adapted from alt-arb
  `pricing/fees.py` @ 594878f). 51 tests pass, including hand-computed zigzag cases. The code was committed (7531df4)
  before its first run on recorded data.

**First run, TEST games only (Oct 13 NHL, 9 clean games — don't count)**
- Spread 1.00¢ before and after the start in every game; X ≈ 1.8–1.9¢.
- Median reversals = 1 (gate needs ≥ 3). Most trade-price changes were bid-ask bounce (e.g. 110 of 127 in PIT@CHI).
- Hand-check of MIN@WPG: mid flat at 49.5¢ for the whole pre-game, then a 15¢ jump at +12 min (likely an early goal),
  then three small wobbles. The detector matched the definitions exactly.
- **Observation for Ian:** under the confirmed reversal definition, a one-way jump followed by a ≥ X pullback
  counts as a reversal (MIN@WPG's goal jump did). That may not match the hypothesis's intent (noise around an
  unchanged fair value). Any change must be decided and recorded **before Oct 17**, noting that it was prompted by
  test data.

**AI use + Ian's judgment**
- Claude proposed the S2 mechanics, wrote the code and tests, and ran it on test games only.
- *Ian's judgment:* confirmed the S2 rules, and chose option (b): reversals whose out leg is a jump (≥ 3 × X) don't
  count. This is an evidence → decision → consequence entry: test data showed a goal jump counting as "noise" →
  jumps are excluded → the gate is stricter. Recorded in `decisions.md` before any counted data.
