"""Unit tests for Ichimoku indicator (causal, no look-ahead)."""

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


def test_ichimoku_conversion_line_exact(engine):
    # conversion_period=3, bar2: HH=12, LL=9 → conv = (12+9)/2 = 10.5
    data = [
        (9, 10, 9, 9.5),
        (10, 11, 10, 10.5),
        (11, 12, 11, 11.5),
    ]
    candles = make_candles([(Decimal(str(o)), Decimal(str(h)),
                             Decimal(str(l)), Decimal(str(c)), 100)
                            for o, h, l, c in data])
    params = IndicatorParameters(
        values={"conversion_period": 3, "base_period": 5, "span_b_period": 5}
    )
    result = engine.calculate("Ichimoku", SYMBOL, TIMEFRAME, candles,
                              parameters=params)
    assert result.values["conversion_line"][2] is not None
    assert abs(result.values["conversion_line"][2] - Decimal("10.5")) < Decimal("0.01")


def test_ichimoku_no_forward_displacement(engine):
    # Span A/B must be causal: value at index i uses only data up to i.
    # Use a spike at the last bar; span_a at earlier indices must NOT reflect it.
    data = [(Decimal(str(100 + i)), Decimal(str(100 + i + 1)),
             Decimal(str(100 + i - 1)), Decimal(str(100 + i)), 100) for i in range(40)]
    # Spike the last bar's high dramatically.
    data[-1] = (Decimal("100"), Decimal("1000"), Decimal("100"), Decimal("100"), 100)
    candles = make_candles(data)
    params = IndicatorParameters(
        values={"conversion_period": 5, "base_period": 10, "span_b_period": 20}
    )
    result = engine.calculate("Ichimoku", SYMBOL, TIMEFRAME, candles,
                              parameters=params)
    span_a = result.values["span_a"]
    # span_a at index 30 (before the spike at 39) must be finite and NOT 1000-scaled.
    assert span_a[30] is not None
    assert span_a[30] < Decimal("200"), f"Span A leaked future spike: {span_a[30]}"


def test_ichimoku_lagging_span_delayed(engine):
    # lagging_span[i] = close[i - base_period] (causal delay).
    params = IndicatorParameters(
        values={"conversion_period": 5, "base_period": 3, "span_b_period": 5}
    )
    data = [(Decimal(str(100 + i)), Decimal(str(100 + i + 1)),
             Decimal(str(100 + i - 1)), Decimal(str(100 + i)), 100) for i in range(10)]
    candles = make_candles(data)
    result = engine.calculate("Ichimoku", SYMBOL, TIMEFRAME, candles,
                              parameters=params)
    lag = result.values["lagging_span"]
    # index 3 → close[0] = 100
    assert lag[3] == Decimal(100)
    # index 0,1,2 → None (delay not yet available)
    assert lag[0] is None and lag[1] is None and lag[2] is None


def test_ichimoku_warmup(engine):
    candles = make_candles([(Decimal(str(100 + i)), Decimal(str(100 + i + 1)),
                             Decimal(str(100 + i - 1)), Decimal(str(100 + i)), 100)
                            for i in range(5)])
    result = engine.calculate("Ichimoku", SYMBOL, TIMEFRAME, candles)
    # span_b_period=52 default → insufficient with 5 candles.
    assert result.readiness.value == "insufficient"
    assert all(v is None for v in result.values["span_b"])
