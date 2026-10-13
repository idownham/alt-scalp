# alt-scalp (Project Coin Toss) — Kalshi Kickoff Market-Making Research

## What this is
Research into whether the price noise around game start on Kalshi sports markets can be captured by
**posting maker orders on both sides** (buy low, sell high within seconds/minutes) after fees and
adverse selection. Sister project of `alt-arb` (cross-venue arbitrage); separate repo, separate rules.

Owner: Ian Downham (GitHub: idownham). Part of a graded class project, so accuracy and a clean
evidence trail matter as much as the result. A well-evidenced "no edge" is a valid outcome.

## Current stage
**S1 — Recorder built; test run Oct 15–16, counted recording from Oct 17.** Full plan: `docs/spec.md`. Timeline + game log: `docs/timeline.xlsx`.
Update this line when the stage changes.

## Scope (decided by owner, 2026-10-13)
- **Venue:** Kalshi only. (Polymarket's ~30 req/min per-IP limit is already used by alt-arb's scanner.)
- **Leagues:** NFL, NBA (regular season only, starts 2026-10-20), NHL.
- **Recorder host:** Ian's laptop (macOS) to start; a second small server later if needed.
- **Sample:** 20 clean games, at least 5 per league.

## Hard rules
1. **Read-only.** No order placement code of any kind. No API keys needed or used at this stage.
   If a later stage ever needs keys: `.env` only (gitignored), never printed, logged, or committed.
2. **No live trading** without a separate, explicit owner decision recorded in `docs/decisions.md`.
3. **Pre-registered criteria are fixed.** The go/no-go criteria in `docs/spec.md` must be confirmed by the owner
   before counted data collection starts and must not be changed after looking at results. If they must change,
   record why in `docs/decisions.md` first.
4. **Never simulate optimistically.** Fill assumptions must be conservative (assume you are last in queue unless the
   trade tape proves otherwise). P&L is always net of Kalshi maker/taker fees for the specific series.
5. **Money as Decimal or integer cents, never float.**
6. **Don't starve other projects.** Stay well under Kalshi's read rate limit (Basic tier ≈ 20 req/s);
   alt-arb's droplet scanner also reads Kalshi from a different IP, but keep usage modest anyway.

## Conventions
- Python 3.11+, `pyproject.toml`, virtualenv in `.venv/`, `pytest`.
- Raw recordings in `data/recordings/` (gitignored; large). Commit summaries/derived stats only.
- The Kalshi client and fee model may be copied from `../alt-arb/src/altarb/venues/kalshi.py`, `http.py`,
  `models.py` and `pricing/fees.py` (laptop path: `~/code/alt/alt-arb`). Copy, then adapt; note the source commit.
- Small, focused commits.

## Docs map
- `docs/spec.md` — hypothesis, stages S0–S3, decisions, timeline, pre-registered criteria
- `docs/timeline.xlsx` — timeline, game recording log with progress counter, decision notes
- `docs/decisions.md` — dated decision log (create on first decision)
- `docs/journal.md` — class journal + AI log (dated entries: work, evidence links, observation,
  decision, AI use + Ian's judgment). Add an entry at the end of every working session.
