from datetime import timedelta
from decimal import Decimal

from altscalp.fees import maker_coefficient, maker_fee_e4
from altscalp.s2 import (
    GameResult, Level, Quote, analyze_game, bounce_share, evaluate_gate, genuine_levels, mid_at, zigzag,
)
from altscalp.recorder import Recorder
from conftest import START, Clock

S = 10**9


def q(t_s, bid, ask):
    return Quote(int(t_s * S), bid, ask)


def path(*mids_every_20s, spread=100):
    """Genuine levels from mids in e4, one every 20 s (all persist ≥ 10 s)."""
    return [Level(i * 20 * S, Decimal(m), spread) for i, m in enumerate(mids_every_20s)]


FIXED_X = lambda x: (lambda level: Decimal(x))  # noqa: E731


def test_maker_fee_matches_fee_schedule():
    coeff = maker_coefficient("quadratic_with_maker_fees", "1")
    assert coeff == Decimal("0.0175")
    assert maker_fee_e4(Decimal(5000), coeff) == Decimal("43.75")  # 0.4375¢ at 50¢
    assert maker_coefficient("quadratic", "1") == 0


def test_flicker_shorter_than_10s_is_not_genuine():
    quotes = [q(0, 5000, 5100), q(5, 5100, 5200), q(8, 5000, 5100), q(30, 5100, 5200), q(45, 5100, 5200)]
    levels = genuine_levels(quotes)
    # 50.5 held 0->5 (5 s, dropped), 51.5 held 5->8 (dropped), 50.5 held 8->30 (kept), 51.5 held 30->45 (kept)
    assert [lvl.mid_e4 for lvl in levels] == [Decimal(5050), Decimal(5150)]
    assert levels[0].t_ns == 8 * S


def test_equal_levels_either_side_of_flicker_merge():
    quotes = [q(0, 5000, 5100), q(12, 5100, 5200), q(14, 5000, 5100), q(30, 5000, 5100)]
    assert [lvl.mid_e4 for lvl in genuine_levels(quotes)] == [Decimal(5050)]


def test_exactly_10s_counts():
    quotes = [q(0, 5000, 5100), q(10, 5100, 5200), q(20, 5100, 5200)]
    assert len(genuine_levels(quotes)) == 2


def test_oscillation_counts_each_turn():
    # X = 2¢ (200 e4). 50 -> 53 -> 50 -> 53 -> 50 turns three times, each back within 20 s.
    zz = zigzag(path(5000, 5300, 5000, 5300, 5000), FIXED_X(200))
    assert len(zz.reversals) == 3
    assert [size for size, _ in zz.legs] == [Decimal(300)] * 3


def test_moves_smaller_than_x_are_ignored():
    zz = zigzag(path(5000, 5150, 5000, 5150, 5000), FIXED_X(200))
    assert zz.reversals == [] and zz.legs == []


def test_slow_return_turns_but_does_not_count():
    levels = [Level(0, Decimal(5000), 100), Level(20 * S, Decimal(5300), 100), Level(400 * S, Decimal(5000), 100),
              Level(420 * S, Decimal(5300), 100)]
    zz = zigzag(levels, FIXED_X(200))
    assert len(zz.legs) == 2  # 50->53 and 53->50 both completed
    assert len(zz.reversals) == 1  # only 53->50->53 (20 s); 50->53->50 took 380 s


def test_out_leg_extends_and_back_measured_from_extreme():
    zz = zigzag(path(5000, 5200, 5400, 5500, 5200), FIXED_X(200))
    [r] = zz.reversals
    assert r.out_e4 == Decimal(500)
    assert r.extreme_t_ns == 60 * S and r.back_t_ns == 80 * S


def test_jump_then_pullback_is_not_a_reversal():
    # Out leg 6¢ = 3 × X: a jump. The 2.5¢ pullback turns the zigzag but isn't counted.
    zz = zigzag(path(5000, 5600, 5350, 5600), FIXED_X(200))
    assert [size for size, _ in zz.legs] == [Decimal(600), Decimal(250)]
    # The pullback leg (5600 -> 5350, 2.5¢ < 3 × X) then reverses back: that one counts.
    assert len(zz.reversals) == 1 and zz.reversals[0].out_e4 == Decimal(250)


def test_just_under_a_jump_still_counts():
    zz = zigzag(path(5000, 5599, 5350), FIXED_X(200))
    assert len(zz.reversals) == 1


def test_swing_starting_with_a_drift_is_caught():
    # 50 -> 49 -> 51 -> 49: the up leg starts from the running low (49), not the first level (50).
    zz = zigzag(path(5000, 4900, 5100, 4900), FIXED_X(200))
    assert len(zz.reversals) == 1
    assert zz.reversals[0].out_e4 == Decimal(200)


def test_x_is_taken_at_the_pivot():
    def x_of(level):
        return Decimal(500) if level.mid_e4 >= 5300 else Decimal(200)

    # Out leg 50 -> 53 uses X(50) = 2¢; back to 50 is 3¢ >= 2¢: one reversal.
    # Then the pivot is 53 with X = 5¢; moves of 3¢ don't count as a new out leg.
    zz = zigzag(path(5000, 5300, 5000, 5300), x_of)
    assert len(zz.reversals) == 1


def test_mid_at_and_bounce():
    quotes = [q(0, 5000, 5100), q(10, 5000, 5100), q(20, 5100, 5200)]
    assert mid_at(quotes, -1) is None
    assert mid_at(quotes, 15 * S) == Decimal(5050)
    trades = [(1 * S, 5100), (2 * S, 5000), (3 * S, 5100), (21 * S, 5200)]
    # 51->50 and 50->51 happen with mid unchanged (bounce); 51->52 crosses a real mid move.
    assert bounce_share(quotes, trades) == (3, 2)


def _result(league, reversals):
    return GameResult("E", league, "2026-10-18T17:00:00.000000Z", "T", True, 0, 0, 0, None, None, None,
                      0, 0, 0, [], [object()] * reversals, [])


def test_gate_uses_pooled_median_and_reports_sample_size():
    results = [_result("NHL", 5)] * 8 + [_result("NFL", 1)] * 6 + [_result("NBA", 4)] * 6
    gate = evaluate_gate(results)
    assert gate.games == 20 and gate.enough_data
    assert gate.median_reversals == 4 and gate.passed
    gate = evaluate_gate(results[:10])
    assert not gate.enough_data


def test_gate_with_no_games():
    assert evaluate_gate([]).passed is None


def test_analyze_game_end_to_end(client, store):
    clock = Clock(START - timedelta(minutes=30))
    rec = Recorder(client, store, clock=clock, sleep=lambda s: None)
    rec.step()  # loads markets and takes one snapshot of the canned book (bid 54¢, ask 62¢)
    r = analyze_game(store, "KXNHLGAME-26OCT19PITUTA")
    assert r.ticker == "KXNHLGAME-26OCT19PITUTA-UTA"  # home market only
    assert r.quotes == 1 and r.spread_pre_median_e4 == 800
    assert r.counted  # scheduled Oct 20 01:00Z, after counted recording starts
