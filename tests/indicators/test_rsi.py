"""Unit tests for RSI indicator (Wilder's method)."""

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


def _up_candles(n=30):
    # Strictly increasing closes → all gains → RSI = 100
    return make_candles([(Decimal(str(100 + i)), Decimal(str(100 + i)),
                          Decimal(str(100 + i)), Decimal(str(100 + i)), 100)
                         for i in range(n)])


def _down_candles(n=30):
    # Strictly decreasing closes → all losses → RSI = 0
    return make_candles([(Decimal(str(100 - i)), Decimal(str(100 - i)),
                          Decimal(str(100 - i)), Decimal(str(100 - i)), 100)
                         for i in range(n)])


def _flat_candles(n=30):
    return make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                          Decimal("100"), 100) for _ in range(n)])


def test_rsi_all_gains_equals_100(engine):
    result = engine.calculate("RSI", SYMBOL, TIMEFRAME, _up_candles())
    assert last_non_none(result.values["rsi"]) == Decimal(100)


def test_rsi_all_losses_equals_0(engine):
    result = engine.calculate("RSI", SYMBOL, TIMEFRAME, _down_candles())
    assert last_non_none(result.values["rsi"]) == Decimal(0)


def test_rsi_flat_equals_50(engine):
    result = engine.calculate("RSI", SYMBOL, TIMEFRAME, _flat_candles())
    assert last_non_none(result.values["rsi"]) == Decimal(50)


def test_rsi_bounds(engine):
    # Mixed data should stay within [0, 100].
    closes = [100, 102, 101, 103, 100, 104, 102, 105, 101, 103,
              100, 102, 101, 104, 100, 103, 101, 105, 102, 104]
    candles = make_candles([(c, c + 1, c - 1, c, 100) for c in closes])
    result = engine.calculate("RSI", SYMBOL, TIMEFRAME, candles)
    series = [v for v in result.values["rsi"] if v is not None]
    for v in series:
        assert Decimal(0) <= v <= Decimal(100), f"RSI out of bounds: {v}"


def test_rsi_warmup(engine):
    # period 14 → need 14 changes → first valid at index 14 (15 candles)
    candles = _up_candles(14)  # only 14 candles → insufficient
    result = engine.calculate("RSI", SYMBOL, TIMEFRAME, candles)
    assert result.readiness.value in ("insufficient", "warming_up")
    assert all(v is None for v in result.values["rsi"])

    candles = _up_candles(15)
    result = engine.calculate("RSI", SYMBOL, TIMEFRAME, candles)
    assert result.readiness.value == "ready"
    assert last_non_none(result.values["rsi"]) == Decimal(100)


def test_rsi_invalid_period(engine):
    from src.indicators.base import IndicatorParameters
    params = IndicatorParameters(values={"period": 1})
    ind = engine.registry.get("RSI")
    with pytest.raises(ValueError):
        ind.validate_parameters(params)
