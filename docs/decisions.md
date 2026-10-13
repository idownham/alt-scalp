# Decisions

Dated log of owner decisions. Newest last. Changes to pre-registered criteria must be recorded here first.

---

## 2026-10-13 — Historical (backfilled) data is out-of-sample only

**Decision (Ian):** option (a) from `docs/s0-research.md` → "Criteria review" item 1.

- Historical Kalshi data for past games (public trade tape via `/markets/trades` and `/historical/trades`, 1-minute
  candlesticks) is **not analysed, plotted, or summarised** until S2 on the recorded sample is complete.
- After that, it may be used only as an **out-of-sample check** of S2 results, at its own resolution (trades + 1-minute
  top-of-book, no depth). It does not count toward the 20-game sample and cannot be used to set or tune criteria.
- Fetching the trade tape for games we *record* (after each window closes) is part of the recording, not historical data.

**Why:** backfill makes it possible to look at results before the criteria are frozen. Keeping it untouched until
S2 is done protects the pre-registration and gives a clean holdout set.

---

## 2026-10-13 — Pre-registered criteria confirmed

**Decision (Ian):** accept all remaining suggestions from `docs/s0-research.md` → "Criteria review" items 2–9. The spec's
criteria section is now marked CONFIRMED. This was decided before any counted data was recorded and before any
historical data was examined.

Changes from the draft:
- **S2 gate:** dropped the "median pre-kickoff spread ≥ 2¢ OR" prong. The gate is now ≥ 3 reversals in the median game.
  Defined *genuine mid move* (persists ≥ 10 s) and *reversal* (≥ X out and ≥ X back within 5 min, X = spread + 2 × maker
  fee at the actual price).
- **Fill rule:** trade-through (last in queue) decides GO/STOP; a queue-volume rule is reported as a sensitivity only.
- **Adverse-selection mark-out:** 60 s is primary; 10 s and 5 min are secondary.
- **GO:** also requires ≥ 100 simulated round trips; a game with 0 fills counts as not positive; a bootstrap 90% CI is reported but not gated.
- **Fees:** per-order ceil-to-cent decides; the exact per-fill fee is a sensitivity.
- **Clean game:** the 30 s gap rule applies to book snapshots only; exclude postponements, trading pauses, and markets with an active liquidity incentive.
- **Window:** extended to +20 min after scheduled start (S1 recorder updated to match).
- **Markets:** analyse and simulate the home team's market only.

Where the suggestions gave example values ("e.g."), those values were adopted: 10 s persistence, 5 min reversal
window, 60 s mark-out, 100 round trips, home-team market. A genuine mid move is defined by persistence only. The
"or both bid and ask move" alternative was not adopted, so there is one unambiguous definition.

**Why:** a 1¢ minimum tick makes a spread threshold a poor tradability test. Precise definitions are needed before
data exists. The extra GO conditions stop a few low-fill games from producing a GO.
