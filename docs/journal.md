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
- None taken. The suggested changes to the draft criteria are listed in `s0-research.md` for Ian to confirm.
- Open for Ian: how historical/backfill data is treated (it must be decided before anyone looks at it).

**AI use + Ian's judgment**
- Claude (Opus 5.5, Claude Code) read the docs, ran the read-only API probes, and drafted `s0-research.md` and this
  entry. Every factual claim cites a doc page or a live API response from 2026-10-13.
- Limitations Claude flagged: the 0.07 base coefficient is inferred from the fee-schedule page's ranges, not quoted
  from the PDF; whether the multi-orderbook endpoint is billed per ticker is unknown; the trade-side skew is from one game only.
- *Ian's judgment:* historical data is out-of-sample only, option (a); all other criteria suggestions accepted →
  pre-registered criteria CONFIRMED in `spec.md` (`decisions.md`, 2026-10-13). Claude used the example values given in
  the suggestions as the concrete thresholds.
