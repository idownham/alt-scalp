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
