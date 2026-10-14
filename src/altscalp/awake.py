"""Keep the Mac awake only when it matters: a game window is open or opens within AWAKE_LEAD.

Outside that, macOS's own sleep settings apply, so a laptop on battery isn't held awake overnight.
`caffeinate` can't stop lid-close sleep on battery; that's on the operator (docs/journal.md, 2026-10-13).
"""

from __future__ import annotations

import os
import subprocess
from datetime import timedelta

AWAKE_LEAD = timedelta(hours=2)


class Caffeinate:
    """Callable switch: Caffeinate()(True) holds a caffeinate assertion, (False) releases it."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def __call__(self, on: bool) -> None:
        if on and self._proc is None:
            # -i: no idle sleep, -s: no system sleep on AC power; -w: exit if we die.
            self._proc = subprocess.Popen(["caffeinate", "-is", "-w", str(os.getpid())])
        elif not on and self._proc is not None:
            self._proc.terminate()
            self._proc.wait(timeout=5)
            self._proc = None

    @property
    def on(self) -> bool:
        return self._proc is not None
