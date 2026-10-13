"""Command line: `altscalp record` (run the recorder), `altscalp status` (coverage per game),
`altscalp schedule` (upcoming windows).
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from altscalp.kalshi import KalshiClient
from altscalp.recorder import Recorder
from altscalp.report import coverage, format_table
from altscalp.store import Store, iso

DEFAULT_DIR = Path("data/recordings")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="altscalp")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="recordings directory (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="run the recorder until stopped (Ctrl-C)")
    rec.add_argument("--interval", type=float, default=2.5, help="seconds between book snapshots (spec: 2-3)")
    rec.add_argument("--home-only", action="store_true", help="snapshot only the home team's market")
    rec.add_argument("--no-caffeinate", action="store_true", help="don't keep the Mac awake")

    sub.add_parser("status", help="recording coverage and clean/not-clean per game")
    sub.add_parser("schedule", help="refresh the schedule and list upcoming windows")

    args = parser.parse_args(argv)
    args.dir.mkdir(parents=True, exist_ok=True)
    db = args.dir / "recordings.sqlite"

    if args.command == "record":
        return _record(args, db)
    store = Store(db)
    try:
        if args.command == "schedule":
            with KalshiClient() as client:
                Recorder(client, store).refresh_schedule()
            now = iso(datetime.now(timezone.utc))
            for g in store.db.execute(
                "SELECT * FROM games WHERE window_end_utc > ? ORDER BY start_utc", (now,)
            ):
                print(f"{g['window_start_utc'][:16]} -> {g['window_end_utc'][11:16]}  {g['league']}  "
                      f"{g['event_ticker']:<28} {g['title']}")
        else:
            print(format_table(coverage(store), iso(datetime.now(timezone.utc))))
    finally:
        store.close()
    return 0


def _record(args: argparse.Namespace, db: Path) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(args.dir / "recorder.log")],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is too noisy at 2.5 s
    lock = open(args.dir / "recorder.lock", "w")  # noqa: SIM115 - held for the life of the process
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another recorder is already running on this directory", file=sys.stderr)
        return 1

    if sys.platform == "darwin" and not args.no_caffeinate:
        # -i: no idle sleep, -s: no system sleep on AC power; -w: exit when we do.
        subprocess.Popen(["caffeinate", "-is", "-w", str(os.getpid())])

    stopping = threading.Event()  # set by Ctrl-C / SIGTERM; also cuts short the recorder's sleeps

    def _stop(*_: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    store = Store(db)
    try:
        with KalshiClient() as client:
            recorder = Recorder(client, store, interval=args.interval, home_only=args.home_only, sleep=stopping.wait)
            recorder.run(stop=stopping.is_set)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
