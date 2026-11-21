"""Unit tests for Stochastic Oscillator indicator."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.indicators.base import IndicatorParameters
from src.market_data.models import MarketTimeframe
from tests.indicators.conftest import make_candles, last_non_none

SYMBOL = "EURUSD"
TIMEFRAME = MarketTimeframe.M1


@pytest.fixture
def engine():
    return create_engine()


def test_stochastic_bounds(engine):
    # Oscillating data: %K and %D must stay in [0, 100].
    data = [
        (10, 11, 9, 10),   # open, high, low, close
        (10, 12, 9, 11),
        (11, 13, 10, 12),
        (12, 14, 11, 13),
        (13, 15, 12, 14),
        (14, 16, 13, 15),
        (15, 17, 14, 16),
        (16, 18, 15, 17),
        (17, 19, 16, 18),
        (18, 20, 17, 19),
        (19, 21, 18, 20),
        (20, 22, 19, 21),
    ]
    candles = make_candles([(Decimal(str(o)), Decimal(str(h)),
                             Decimal(str(l)), Decimal(str(c)), 100)
                            for o, h, l, c in data])
    result = engine.calculate("Stochastic", SYMBOL, TIMEFRAME, candles)
    for name in ("k", "d"):
        series = [v for v in result.values[name] if v is not None]
        for v in series:
            assert Decimal(0) <= v <= Decimal(100), f"{name} out of bounds: {v}"


def test_stochastic_zero_denominator(engine):
    # Flat range: HH == LL → raw_k = 0.
    candles = make_candles([(Decimal("10"), Decimal("10"), Decimal("10"),
                             Decimal("10"), 100) for _ in range(20)])
    result = engine.calculate("Stochastic", SYMBOL, TIMEFRAME, candles)
    series = [v for v in result.values["k"] if v is not None]
    assert all(v == Decimal(0) for v in series)


def test_stochastic_exact_raw_k(engine):
    # k_period=3, k_smoothing=1, d_period=1 → raw_k exposed directly in k.
    # bar2: HH=12, LL=9, close=11.5 → k = (11.5-9)/(12-9)*100 = 83.333...
    data = [
        (9, 10, 9, 9.5),
        (10, 11, 10, 10.5),
        (11, 12, 11, 11.5),
    ]
    candles = make_candles([(Decimal(str(o)), Decimal(str(h)),
                             Decimal(str(l)), Decimal(str(c)), 100)
                            for o, h, l, c in data])
    params = IndicatorParameters(
        values={"k_period": 3, "k_smoothing": 1, "d_period": 1}
    )
    result = engine.calculate("Stochastic", SYMBOL, TIMEFRAME, candles,
                              parameters=params)
    # index 2 is first valid.
    assert result.values["k"][2] is not None
    expected = Decimal(11.5) - Decimal(9)
    expected = expected / Decimal(3) * Decimal(100)
    assert abs(result.values["k"][2] - expected) < Decimal("0.01")


def test_stochastic_warmup(engine):
    candles = make_candles([(Decimal("10"), Decimal("11"), Decimal("9"),
                             Decimal("10"), 100) for _ in range(3)])
    result = engine.calculate("Stochastic", SYMBOL, TIMEFRAME, candles)
    # k_period=14 → insufficient.
    assert result.readiness.value == "insufficient"
    assert all(v is None for v in result.values["k"])
