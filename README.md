# alt-scalp — Project Coin Toss

Research project: can the price noise around kickoff on Kalshi sports markets (NFL, NBA, NHL) be captured
by quoting both sides as a maker, after fees and adverse selection?

Read-only research — no trading. See `docs/spec.md` for the plan and `CLAUDE.md` for project rules.

Sister project: [`alt-arb`](https://github.com/idownham/alt-arb) (Kalshi ↔ Polymarket US arbitrage scanner).

## Recorder (S1)

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/altscalp schedule     # refresh the schedule, list upcoming windows
.venv/bin/altscalp record       # run until Ctrl-C; keeps the Mac awake (caffeinate)
.venv/bin/altscalp status       # per-game coverage: snapshots, max gap, trades, CLEAN / not-clean
.venv/bin/pytest                # unit tests (add -m live for one real-API check)
```

- Reads only public, unauthenticated endpoints. There are no keys and no order code.
- Finds every NFL/NHL/NBA (regular-season) game from Kalshi milestones and records each from 30 min before to
  20 min after scheduled start. It takes one batched order-book snapshot every 2.5 s, then fetches the game's
  trade tape after the window closes.
- Everything goes to `data/recordings/recordings.sqlite` (gitignored), and the log goes to
  `data/recordings/recorder.log`. All state is in the database, so a restart just resumes.
- **Counted recording runs on a cloud server:** see `docs/deploy.md`. On the laptop, auto-restart is
  `scripts/com.idownham.altscalp.recorder.plist` (install steps inside).
- Keep the laptop **plugged in with the lid open**. `caffeinate` can't stop sleep when the lid is closed on battery.
