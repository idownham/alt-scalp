"""Kalshi fee coefficients by series fee type.

Adapted from alt-arb `src/altarb/pricing/fees.py` @ 594878f (Kalshi part only). The 0.07 base is
confirmed against kalshi.com/fee-schedule (docs/s0-research.md, question 1):

    taker fee per contract = 0.07 × M × P × (1 − P)
    maker fee per contract = taker × 0.25 under quadratic_with_maker_fees (0.0175·P·(1−P) at M = 1)

Values are Decimal; S3 adds the per-order rounding.
"""

from __future__ import annotations

from decimal import Decimal

KALSHI_TAKER = Decimal("0.07")
KALSHI_MAKER_RATIO = {
    "quadratic": Decimal("0"),
    "quadratic_with_maker_fees": Decimal("0.25"),
    "quadratic_with_combo_maker_fees": Decimal("0.5"),
}


class UnsupportedFeeType(ValueError):
    """A fee structure this model can't price. Skip the market rather than guess."""


def maker_coefficient(fee_type: str, multiplier: Decimal | str) -> Decimal:
    if fee_type not in KALSHI_MAKER_RATIO:
        raise UnsupportedFeeType(f"Kalshi fee_type {fee_type!r} is not modeled")
    return KALSHI_TAKER * Decimal(multiplier) * KALSHI_MAKER_RATIO[fee_type]


def maker_fee_e4(mid_e4: Decimal, coefficient: Decimal) -> Decimal:
    """Exact (unrounded) maker fee per contract, in 1/10,000 dollar, at price mid_e4."""
    p = mid_e4 / 10_000
    return coefficient * p * (1 - p) * 10_000
