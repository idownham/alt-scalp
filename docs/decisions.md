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

## 2026-11-08 — Recorder moves to the shared droplet `alt-arb`

**Evidence:** since counted recording began on Oct 17, `altscalp status` marks 168 of 365 game windows not clean
(197 clean: NBA 83, NFL 39, NHL 75). The recorder log shows 17–86 "machine asleep or network stalled" warnings a
day from Oct 31 to Nov 8. That's the laptop sleeping, the same failure mode as Oct 13–14.

**Decision (Ian, in chat, 2026-11-08):** run the recorder on the resized shared droplet (HQ decision 2026-10-15;
Ian resized it to 1 vCPU / 2 GB / 50 GB the same evening) instead of the laptop or a separate server. It's set up
from this HQ session at Ian's request, not from a Coin Toss session. This supersedes "Recorder host: laptop for now"
(2026-10-14), and the separate-IP note in CLAUDE.md rule 6 no longer holds.

**Consequence:**
- Server recording starts 2026-11-09 04:40 UTC (`altscalp-recorder`, user `altscalp`, `/opt/alt-scalp`, 57 tests passed,
  chrony clock sync). No game window was open; the next one opens 2026-11-09 23:30 UTC.
- The laptop recorder keeps running as a backup until the first server window is verified clean, then it's unloaded.
  From the cutover, the server DB is the source of truth. The laptop DB is kept as is, and windows are never mixed between hosts.
- The pre-registered criteria are unchanged.

---

## 2026-11-09 — S2 verdict: STOP

**Evidence:** `docs/s2-results.md`, with per-game output in `docs/s2-games.txt`. `altscalp analyze` at `014c442` ran on a
frozen copy of the laptop DB (2026-11-09 05:12 UTC). The sample is 196 counted clean games (NBA 83, NFL 39, NHL 74) and
meets the enough-data rule. **Median reversals = 0** against the pre-registered ≥ 3. Only 22 games (11%) reach 3, and
112 have none. Per league the medians are NBA 1, NFL 0 and NHL 0. Spreads sit at the 1¢ tick, so X ≈ 1.8¢. 94% of
trade-price changes are bid-ask bounce. All 82 jumps came after the scheduled start. Descriptive only: without the jump
exclusion the median would be 2, which still fails.

**Decision (Ian, in chat, 2026-11-09):** confirmed **STOP** at S2. The noise around game start isn't tradable under
the pre-registered definition. S3 (maker simulation) isn't run, and no live trading is considered.

**Notes:**
- The counted sample is 196, not the 197 in the 2026-11-08 entries. PIT@COL (01:00 UTC Oct 17 = Oct 16 CT) is a test
  game under rule 5 of "S2 implementation details". The code already applied that rule; no rule was reinterpreted.
- Trading pauses weren't checked by hand (the DB has no market status). This can't change the median (see results doc).
- No criterion or threshold was changed.

**Consequence:** Coin Toss ends at S2 with a well-evidenced "no edge". These are still open owner decisions, not
decided here:
- whether the droplet and laptop recorders keep running;
- whether the historical data is used as the out-of-sample check (decisions.md 2026-10-13).

## 2026-11-10 — Stop recording

**Decision (Ian, 2026-11-09: "take over" on the HQ recommendation):** with S2 = STOP there is no S3, so recording has
no further use. The server recorder and `altscalp-update.timer` were stopped and disabled at 2026-11-10 03:28:57 UTC,
after the last window's trades were fetched and with no window open. The laptop launchd agent is unloaded.
**Archive:** the server DB (2026-11-09 04:40 → 11-10 03:29 UTC; 12 windows, all CLEAN; sha256
`481cebda49bd1bb77658c04339a2a91a23fb196ba6336ec4261de179bc5f3cd6`) is at `data/recordings/server/recordings.sqlite`
(gitignored). It also stays on the droplet. These windows came after S2 and aren't part of its sample. The laptop DB
is unchanged.
**Server trial result:** the first server windows (Nov 9 evening) were all clean, which confirms the move fixed the sleep problem.
