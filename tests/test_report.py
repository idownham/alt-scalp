from altscalp.report import max_gap_seconds

S = 1_000_000_000


def test_gap_includes_window_edges():
    assert max_gap_seconds([10 * S, 12 * S], 0, 20 * S) == 10.0  # start -> first snapshot
    assert max_gap_seconds([1 * S, 3 * S], 0, 20 * S) == 17.0  # last snapshot -> end


def test_snapshots_outside_window_ignored():
    assert max_gap_seconds([-5 * S, 25 * S], 0, 20 * S) is None


def test_regular_snapshots():
    times = [i * 2 * S for i in range(11)]
    assert max_gap_seconds(times, 0, 20 * S) == 2.0
