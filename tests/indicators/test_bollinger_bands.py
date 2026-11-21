"""Unit tests for Bollinger Bands indicator."""

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
    return IndicatorParameters(values={"period": 3, "multiplier": 2.0})


def test_bollinger_exact_values(engine):
    # period=3, multiplier=2, closes [10, 12, 14]:
    # middle = 12
    # std = sqrt(((10-12)^2+(12-12)^2+(14-12)^2)/3) = sqrt(8/3) ≈ 1.633
    # upper ≈ 15.266, lower ≈ 8.734
    data = [
        (9, 10, 9, 10),
        (11, 12, 11, 12),
        (13, 14, 13, 14),
    ]
    candles = make_candles([(Decimal(str(o)), Decimal(str(h)),
                             Decimal(str(l)), Decimal(str(c)), 100)
                            for o, h, l, c in data])
    result = engine.calculate("Bollinger Bands", SYMBOL, TIMEFRAME, candles,
                              parameters=_period3_params())
    middle = result.values["middle"][2]
    upper = result.values["upper"][2]
    lower = result.values["lower"][2]
    assert middle is not None and abs(middle - Decimal(12)) < Decimal("0.001")
    assert upper is not None and abs(upper - Decimal("15.266")) < Decimal("0.01")
    assert lower is not None and abs(lower - Decimal("8.734")) < Decimal("0.01")


def test_bollinger_bandwidth_percent_b(engine):
    data = [
        (9, 10, 9, 10),
        (11, 12, 11, 12),
        (13, 14, 13, 14),
    ]
    candles = make_candles([(Decimal(str(o)), Decimal(str(h)),
                             Decimal(str(l)), Decimal(str(c)), 100)
                            for o, h, l, c in data])
    result = engine.calculate("Bollinger Bands", SYMBOL, TIMEFRAME, candles,
                              parameters=_period3_params())
    bw = result.values["bandwidth"][2]
    pb = result.values["percent_b"][2]
    assert bw is not None and bw > 0
    assert pb is not None and Decimal(0) <= pb <= Decimal(1)


def test_bollinger_constant_price(engine):
    candles = make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                             Decimal("100"), 100) for _ in range(25)])
    result = engine.calculate("Bollinger Bands", SYMBOL, TIMEFRAME, candles)
    # std = 0 → upper == middle == lower; percent_b = 0.5.
    mids = [v for v in result.values["middle"] if v is not None]
    ups = [v for v in result.values["upper"] if v is not None]
    lows = [v for v in result.values["lower"] if v is not None]
    for m, u, l in zip(mids, ups, lows):
        assert m == u == l
    pbs = [v for v in result.values["percent_b"] if v is not None]
    assert all(v == Decimal("0.5") for v in pbs)
