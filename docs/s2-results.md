# S2 results — is there tradable noise around game start?

*Run 2026-11-09 (UTC) by Claude in a Coin Toss session, at Ian's request. Verdict status: **STOP per the
pre-registered gate**, pending Ian's confirmation (see `decisions.md`).*

## What was run
- Code: `altscalp analyze` (`src/altscalp/s2.py`, last changed in `70cbfcf`; repo at `014c442`). 57 tests pass.
  No code, criterion or threshold was changed for this run.
- Data: a frozen copy of the laptop DB `data/recordings/recordings.sqlite`, taken 2026-11-09 05:12 UTC with
  `sqlite3 .backup` (the laptop recorder was still running as a backup, so the live file was not analysed directly).
- Rules: `docs/spec.md` (pre-registered criteria, confirmed 2026-10-13) and `docs/decisions.md` "S2 implementation
  details" rules 1–7 plus rule 8 (jump exclusion), extended to either move (all 2026-10-14). Home market only.
- Per-game output: `docs/s2-games.txt` (one row per game, as printed by `altscalp analyze`).

## Sample
| League | Counted clean games | Counted not clean |
|---|---:|---:|
| NBA | 83 | 63 |
| NFL | 39 | 16 |
| NHL | 74 | 88 |
| **Total** | **196** | **167** |

- Counted = scheduled start ≥ 2026-10-17 05:00 UTC (Oct 17 00:00 CT, decisions.md rule 5) and CLEAN per
  `altscalp status`. First counted clean game 2026-10-18 17:00 UTC, last 2026-11-09 02:00 UTC.
- **Correction to the 197 in the 2026-11-08 journal entry:** that count included PIT@COL (start 2026-10-17 01:00 UTC
  = Oct 16, 20:00 CT). Under rule 5 it is a test game, so the counted sample is 196 (NHL 74, not 75). The code
  already applies rule 5; nothing was reinterpreted.
- Enough-data criterion (≥ 20 clean games, ≥ 5 per league): **met**.

## The gate
**Pre-registered:** continue to S3 only if the median game (all leagues pooled) has ≥ 3 reversals in the window.

| | Games | Median reversals | Mean | Max | Games with ≥ 3 | Games with 0 |
|---|---:|---:|---:|---:|---:|---:|
| **All (decides)** | 196 | **0** | 0.90 | 6 | 22 (11%) | 112 (57%) |
| NBA | 83 | 1 | 1.53 | 6 | 17 | 27 |
| NFL | 39 | 0 | 0.95 | 4 | 5 | 22 |
| NHL | 74 | 0 | 0.16 | 2 | 0 | 63 |

Per-league medians are reported but don't decide the gate (rule 6). No league reaches 3.

**Result: median 0 < 3 → STOP. The noise isn't tradable under the pre-registered definition.**

## What the markets looked like (descriptive)
| | All | NBA | NFL | NHL |
|---|---|---|---|---|
| Median spread before start (median of per-game medians) | 1.00¢ | 1.00¢ | 1.00¢ | 1.00¢ |
| Median spread after start | 1.00¢ | 1.00¢ | 1.00¢ | 1.00¢ (one game 2.00¢) |
| X = spread + 2 × maker fee (median of per-game medians; range) | 1.82¢ (1.24–2.13) | 1.78¢ | 1.79¢ | 1.85¢ |
| Raw mid changes per game (median) | 33 | 32 | 38 | 30.5 |
| Genuine moves (level held ≥ 10 s) per game (median) | 13 | 16 | 16 | 8 |
| Out legs ≥ X per game (median) | 2 | 3 | 3 | 0 |
| Trade-price changes with an unchanged mid (bid-ask bounce) | 94.1% of 43,248 | 91.6% | 97.7% | 80.8% |
| Jumps (single genuine move ≥ 3 × X) | 82 in 64 games | 15 | 33 | 34 |
| …of which before scheduled start | 0 | 0 | 0 | 0 |
| Median time for a counted reversal to come back | 38 s | 29 s | 60 s | 98 s |

Plain reading:
- The spread is pinned at the 1¢ minimum tick in nearly every game, so X is ~1.8¢: the mid has to move about two
  ticks out and two back.
- Most visible price action is bid-ask bounce: 94% of trade-price changes happen with the mid unchanged.
- Before the start the mid barely moves. All 82 jumps came after the scheduled start (game events), which is the
  adverse-selection risk the spec warned about. Jumps weren't cause-tagged by hand in this run (rule 7 is
  descriptive only and doesn't affect the gate).
- Of 463 out legs ≥ X, 168 (36%) were jump-sized (≥ 3 × X).

## Sensitivity (descriptive only — not the pre-registered rule, doesn't decide anything)
Without the jump exclusion (rule 8 and its extension), the pooled median would be **2** reversals (79 of 196 games
≥ 3; NBA median 3, NFL 3, NHL 0). So even under the looser rule that existed before 2026-10-14, the pooled gate
would still fail. Most of the gap between 176 counted reversals and 444 unexcluded ones is jump-driven swings after
the start, which is the adverse-selection case rather than noise.

## Known biases and caveats
- **Not-clean windows excluded (167 of 363 counted windows, 46%).** Almost all were laptop sleep or network stalls
  (journal 2026-11-08). Exclusion depends on when the laptop was awake, not on market behaviour, so it's unlikely to
  bias reversal counts in a particular direction, but the clean set over-represents times Ian's laptop was open
  (afternoon/evening Central time) and under-represents NHL (88 of 162 NHL windows not clean).
- **Trading pauses weren't checked by hand** for the 196 games (rule 5 says they are). The DB doesn't store market
  status. With 112 games at 0 reversals and only 22 at ≥ 3, dropping a handful of paused games can't move the
  median to 3.
- **Incentives / reschedules:** the `incentives` table is empty for the period; 3 events had schedule changes and are
  already excluded by the clean rule.
- **Single host, single source:** all counted data is from the laptop recorder. The droplet recorder (from
  2026-11-09 04:40 UTC) has no completed windows yet and isn't part of this sample.
- **Historical data** (out-of-sample check, decisions.md 2026-10-13) was not used. It may now be used as a check,
  but the gate result doesn't depend on it.
- **Late analysis:** S2 was planned for Oct 22–24 and run on 2026-11-09. The criteria were fixed on 2026-10-13/14
  and weren't changed; the delay only means far more games than the 20 required.

## Verdict
**STOP at S2 (pre-registered gate failed: median reversals 0 vs ≥ 3 required).** S3 maker simulation is not run.
This becomes the project's decision only after Ian confirms it (`decisions.md`).
