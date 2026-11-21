"""Unit tests for ADX indicator."""

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


def test_adx_constant_price_zeros(engine):
    # No directional movement → +DM=-DM=0 → +DI=-DI=0 → DX=0 → ADX=0.
    candles = make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                             Decimal("100"), 100) for _ in range(40)])
    result = engine.calculate("ADX", SYMBOL, TIMEFRAME, candles)
    adx = [v for v in result.values["adx"] if v is not None]
    pdi = [v for v in result.values["plus_di"] if v is not None]
    mdi = [v for v in result.values["minus_di"] if v is not None]
    assert all(v == Decimal(0) for v in adx), f"ADX not zero: {adx}"
    assert all(v == Decimal(0) for v in pdi), f"+DI not zero: {pdi}"
    assert all(v == Decimal(0) for v in mdi), f"-DI not zero: {mdi}"


def test_adx_bounds(engine):
    # Trending data → all outputs in [0, 100].
    data = []
    price = Decimal(100)
    for i in range(50):
        price += Decimal(1)
        data.append((price, price + 2, price - 1, price))
    candles = make_candles([(Decimal(str(o)), Decimal(str(h)),
                             Decimal(str(l)), Decimal(str(c)), 100)
                            for o, h, l, c in data])
    result = engine.calculate("ADX", SYMBOL, TIMEFRAME, candles)
    for name in ("adx", "plus_di", "minus_di"):
        series = [v for v in result.values[name] if v is not None]
        for v in series:
            assert Decimal(0) <= v <= Decimal(100), f"{name} out of bounds: {v}"


def test_adx_warmup(engine):
    # period=14 → first ADX at index 27 (2*14-1). 28 candles → warming_up.
    candles = make_candles([(Decimal(str(100 + i)), Decimal(str(100 + i + 2)),
                             Decimal(str(100 + i - 1)), Decimal(str(100 + i)), 100)
                            for i in range(28)])
    result = engine.calculate("ADX", SYMBOL, TIMEFRAME, candles)
    assert result.readiness.value == "warming_up"
    # 29 candles → first valid ADX at index 27 → ready.
    candles = make_candles([(Decimal(str(100 + i)), Decimal(str(100 + i + 2)),
                             Decimal(str(100 + i - 1)), Decimal(str(100 + i)), 100)
                            for i in range(29)])
    result = engine.calculate("ADX", SYMBOL, TIMEFRAME, candles)
    assert result.readiness.value == "ready"
    assert last_non_none(result.values["adx"]) is not None


def test_adx_invalid_period(engine):
    params = IndicatorParameters(values={"period": 1})
    ind = engine.registry.get("ADX")
    with pytest.raises(ValueError):
        ind.validate_parameters(params)
