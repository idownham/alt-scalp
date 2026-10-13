from datetime import timedelta

from altscalp.recorder import Recorder
from altscalp.report import coverage, max_gap_seconds
from altscalp.store import iso
from conftest import START, Clock

S = 1_000_000_000


def test_gap_includes_window_edges():
    assert max_gap_seconds([10 * S, 12 * S], 0, 20 * S) == 10.0  # start -> first snapshot
    assert max_gap_seconds([1 * S, 3 * S], 0, 20 * S) == 17.0  # last snapshot -> end


def test_snapshots_outside_window_ignored():
    assert max_gap_seconds([-5 * S, 25 * S], 0, 20 * S) is None


def test_regular_snapshots():
    times = [i * 2 * S for i in range(11)]
    assert max_gap_seconds(times, 0, 20 * S) == 2.0


def test_verdict_waits_for_window_to_close(client, store):
    Recorder(client, store, clock=Clock(START - timedelta(minutes=80)), sleep=lambda s: None).step()
    [cov] = coverage(store)
    assert cov.verdict(iso(START - timedelta(minutes=31))) == "upcoming"
    assert cov.verdict(iso(START)) == "recording"
    assert cov.verdict(iso(START + timedelta(minutes=20))) == "not-clean"  # never recorded
