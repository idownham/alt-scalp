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

---

## 2026-10-14 — S2 implementation details (proposed by Claude; CONFIRMED by Ian 2026-10-14, see next entry)

The confirmed criteria leave some mechanics open. These are fixed here **before the S2 code has been run on any
data**: not on test games, not on counted games, and not on historical data. That way the choice can't be shaped by
results. None of them changes a threshold.

1. **Mid** = (best YES bid + best YES ask) / 2 from each snapshot of the home market. Snapshots with an empty side are skipped.
2. **Genuine level:** a mid value whose run lasts ≥ 10 s, measured from the run's first snapshot to the first snapshot
   with a different mid (for the final run, to the last snapshot). Shorter runs are flicker/bounce and are dropped.
   Consecutive equal genuine levels merge. A *genuine mid move* is a change between consecutive genuine levels.
3. **X** = spread + 2 × maker fee, both taken at the pivot (the genuine level where the move starts). The maker fee is
   the exact per-contract formula for the market's recorded series fee (0.07 × multiplier × 0.25 × P × (1 − P) for
   `quadratic_with_maker_fees`, i.e. 0.0175·P·(1−P)), unrounded.
4. **Reversal (zigzag rule):** track a pivot. While no out leg is under way, the pivot is the running low (for an up
   leg) or high (for a down leg) since the last turn. An *out leg* is a move of ≥ X(pivot) away from the pivot,
   extended while the mid keeps going the same way (the extreme and its time update). A *reversal* is counted when the mid comes
   back ≥ X from the extreme within 5 min of the time the extreme was set. The extreme then becomes the new pivot, and
   the back leg is the next potential out leg, so each turn counts once. A back move of ≥ X that takes longer than
   5 min still turns the zigzag, but doesn't count.
5. **Counted games:** scheduled start ≥ 2026-10-17 00:00 CT (05:00Z), regular season, and CLEAN per
   `altscalp status`. Trading pauses are checked by hand. Games before that are test games and are reported separately, if at all.
6. **"Median game"** = the median reversal count across all counted clean games, all leagues pooled. Per-league
   medians are reported but don't decide the gate.
7. **Pre/post start** splits use the scheduled start. *Jumps* (descriptive only) are genuine moves ≥ 3 × X; they're
   listed with time relative to scheduled start for manual cause-tagging.

---

## 2026-10-14 — S2 rules confirmed; jumps don't count as reversals

**Decision (Ian):** the S2 implementation details above are confirmed, with one change:

8. **A reversal whose out leg is a jump (out leg ≥ 3 × X at its pivot) is not counted.** The zigzag still turns there,
   and the leg still appears in the swing-size distribution and the jump list.

**Why:** the hypothesis is about noise around an unchanged fair value. A one-way jump (e.g. a goal) followed by a
small pullback isn't that noise; a maker on the wrong side gets run over by it. This makes the gate stricter, not
looser.

**Disclosure:** this change was prompted by looking at **test** data. The first S2 run on the Oct 13 NHL test games
(not counted) showed MIN@WPG's 15¢ goal jump plus a 2.5¢ pullback counting as a reversal. It was decided before any
counted data exists (counted recording starts 2026-10-17). The spec's reversal definition was updated to match.

---

## 2026-10-14 — Jump exclusion extended to either move

**Decision (Ian):** rule 8 now applies to **both** moves. A reversal is not counted if its out leg **or** its back
move is a jump (≥ 3 × X, using the reversal's X). The back move is measured at its full size: from the extreme to
the furthest point reached before the zigzag next turns or the window ends. Measuring it only at the point it
first passes X would miss a crash that arrives as a small step followed by a large one.

**Why:** a small rise followed by a goal crash is the same adverse-selection event as a jump followed by a pullback,
just in mirror image. The rule should treat them the same. This makes the gate stricter.

**Disclosure:** Claude raised this gap while implementing rule 8 (same session, 2026-10-14). It wasn't prompted by
any particular game; no counted data exists yet.

---

## 2026-10-14 — Recorder host: laptop for now

**Decision (Ian):** counted recording from Oct 17 runs on the laptop (launchd agent), not a cloud server, until Ian
decides otherwise. The server setup in `docs/deploy.md` stays ready but unused.

**Consequence:** a game is only clean if the laptop is awake, plugged in and lid-open for its whole window. Claude
gave Ian a day-by-day schedule of windows (Central time). Kalshi lists games only about a week ahead, so the schedule
for Oct 21 onward (including most NBA opening-week games) has to be refreshed later.
