"""Unit tests for EMA indicator."""

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


def test_ema_default_periods(engine):
    ind = engine.registry.get("EMA")
    assert ind.name == "EMA"
    assert ind.warmup_periods == 199
    assert ind.default_parameters.get("periods") == [9, 20, 50, 100, 200]


def test_ema_known_values(engine):
    # Linear data: EMA(5) with SMA seed -> [None x4, 12,13,14,...,18]
    closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    candles = make_candles([(c, c, c, c, 100) for c in closes])
    params = IndicatorParameters(values={"periods": [5]})
    result = engine.calculate("EMA", SYMBOL, TIMEFRAME, candles, parameters=params)
    ema5 = result.values["ema_5"]
    expected = [None, None, None, None,
                Decimal(12), Decimal(13), Decimal(14), Decimal(15),
                Decimal(16), Decimal(17), Decimal(18)]
    assert ema5 == expected, f"EMA(5) mismatch: {ema5}"


def test_ema_constant_price(engine):
    candles = make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                             Decimal("100"), 100) for _ in range(30)])
    result = engine.calculate("EMA", SYMBOL, TIMEFRAME, candles)
    assert last_non_none(result.values["ema_20"]) == Decimal("100")


def test_ema_invalid_period(engine):
    params = IndicatorParameters(values={"periods": [0]})
    ind = engine.registry.get("EMA")
    with pytest.raises(ValueError):
        ind.validate_parameters(params)
