"""Unit tests for CCI indicator."""

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


def _period3_params():
    return IndicatorParameters(values={"period": 3})


def test_cci_exact_value(engine):
    # period=3:
    # bar0 TP=(10+9+9)/3=28/3; bar1 TP=(11+10+10)/3=31/3; bar2 TP=(12+11+11)/3=34/3
    # SMA_TP[2] = 31/3; mean_dev[2] = (|28/3-31/3|+0+|34/3-31/3|)/3 = (1+0+1)/3=2/3
    # CCI[2] = (34/3 - 31/3) / (0.015 * 2/3) = 1 / 0.01 = 100
    data = [
        (9, 10, 9, 9),
        (10, 11, 10, 10),
        (11, 12, 11, 11),
    ]
    candles = make_candles([(Decimal(str(o)), Decimal(str(h)),
                             Decimal(str(l)), Decimal(str(c)), 100)
                            for o, h, l, c in data])
    result = engine.calculate("CCI", SYMBOL, TIMEFRAME, candles,
                              parameters=_period3_params())
    assert result.values["cci"][2] is not None
    assert abs(result.values["cci"][2] - Decimal(100)) < Decimal("0.01")


def test_cci_zero_denominator(engine):
    # Constant price → TP constant → mean_dev = 0 → CCI = 0.
    candles = make_candles([(Decimal("10"), Decimal("10"), Decimal("10"),
                             Decimal("10"), 100) for _ in range(25)])
    result = engine.calculate("CCI", SYMBOL, TIMEFRAME, candles)
    series = [v for v in result.values["cci"] if v is not None]
    assert all(v == Decimal(0) for v in series)


def test_cci_warmup(engine):
    candles = make_candles([(Decimal("10"), Decimal("10"), Decimal("10"),
                             Decimal("10"), 100) for _ in range(3)])
    result = engine.calculate("CCI", SYMBOL, TIMEFRAME, candles)
    assert result.readiness.value == "insufficient"
    assert all(v is None for v in result.values["cci"])


def test_cci_invalid_period(engine):
    params = IndicatorParameters(values={"period": 1})
    ind = engine.registry.get("CCI")
    with pytest.raises(ValueError):
        ind.validate_parameters(params)
