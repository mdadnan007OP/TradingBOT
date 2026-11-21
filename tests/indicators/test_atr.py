"""Unit tests for ATR indicator (Wilder's smoothing)."""

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


def test_atr_exact_value(engine):
    # period=3:
    # bar0 TR = 10-9 = 1
    # bar1 TR = max(11-10=1, |11-9|=2, |10-9|=1) = 2
    # bar2 TR = max(12-11=1, |12-10|=2, |11-10|=1) = 2
    # ATR[2] = (1+2+2)/3 = 5/3 = 1.666...
    data = [
        (9, 10, 9, 9),
        (10, 11, 10, 10),
        (11, 12, 11, 11),
    ]
    candles = make_candles([(Decimal(str(o)), Decimal(str(h)),
                             Decimal(str(l)), Decimal(str(c)), 100)
                            for o, h, l, c in data])
    result = engine.calculate("ATR", SYMBOL, TIMEFRAME, candles,
                              parameters=_period3_params())
    assert result.values["atr"][2] is not None
    expected = Decimal(5) / Decimal(3)
    assert abs(result.values["atr"][2] - expected) < Decimal("0.01")


def test_atr_constant_price(engine):
    # H==L==C → TR = 0 → ATR = 0.
    candles = make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                             Decimal("100"), 100) for _ in range(25)])
    result = engine.calculate("ATR", SYMBOL, TIMEFRAME, candles)
    series = [v for v in result.values["atr"] if v is not None]
    assert all(v == Decimal(0) for v in series)


def test_atr_warmup(engine):
    candles = make_candles([(Decimal("10"), Decimal("11"), Decimal("9"),
                             Decimal("10"), 100) for _ in range(3)])
    result = engine.calculate("ATR", SYMBOL, TIMEFRAME, candles)
    assert result.readiness.value == "insufficient"
    assert all(v is None for v in result.values["atr"])
