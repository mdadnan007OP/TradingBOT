"""Unit tests for Williams %R indicator."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.indicators.base import IndicatorParameters
from src.market_data.models import MarketTimeframe
from tests.indicators.conftest import make_candles

SYMBOL = "EURUSD"
TIMEFRAME = MarketTimeframe.M1


@pytest.fixture
def engine():
    return create_engine()


def _period3_params():
    return IndicatorParameters(values={"period": 3})


def test_williams_r_exact_value(engine):
    # period=3, bar2: HH=12, LL=9, close=11.5
    # %R = (12 - 11.5)/(12-9) * -100 = 0.5/3 * -100 = -16.666...
    data = [
        (9, 10, 9, 9.5),
        (10, 11, 10, 10.5),
        (11, 12, 11, 11.5),
    ]
    candles = make_candles([(Decimal(str(o)), Decimal(str(h)),
                             Decimal(str(l)), Decimal(str(c)), 100)
                            for o, h, l, c in data])
    result = engine.calculate("Williams %R", SYMBOL, TIMEFRAME, candles,
                              parameters=_period3_params())
    assert result.values["williams_r"][2] is not None
    expected = Decimal("0.5") / Decimal(3) * Decimal(-100)
    assert abs(result.values["williams_r"][2] - expected) < Decimal("0.01")


def test_williams_r_bounds(engine):
    data = [
        (9, 10, 9, 9.5),
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
    result = engine.calculate("Williams %R", SYMBOL, TIMEFRAME, candles)
    series = [v for v in result.values["williams_r"] if v is not None]
    for v in series:
        assert Decimal(-100) <= v <= Decimal(0), f"%R out of bounds: {v}"


def test_williams_r_zero_denominator(engine):
    candles = make_candles([(Decimal("10"), Decimal("10"), Decimal("10"),
                             Decimal("10"), 100) for _ in range(20)])
    result = engine.calculate("Williams %R", SYMBOL, TIMEFRAME, candles)
    series = [v for v in result.values["williams_r"] if v is not None]
    assert all(v == Decimal(0) for v in series)


def test_williams_r_warmup(engine):
    candles = make_candles([(Decimal("10"), Decimal("11"), Decimal("9"),
                             Decimal("10"), 100) for _ in range(3)])
    result = engine.calculate("Williams %R", SYMBOL, TIMEFRAME, candles)
    assert result.readiness.value == "insufficient"
    assert all(v is None for v in result.values["williams_r"])
