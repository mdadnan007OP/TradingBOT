"""Unit tests for MACD indicator."""

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


def test_macd_relationship(engine):
    # macd_line must equal fast_ema - slow_ema; histogram = macd - signal.
    closes = [float(v) for v in range(10, 41)]  # 30 values
    candles = make_candles([(Decimal(str(c)), Decimal(str(c)), Decimal(str(c)),
                             Decimal(str(c)), 100) for c in closes])

    params = IndicatorParameters(
        values={"fast_period": 5, "slow_period": 12, "signal_period": 3}
    )
    result = engine.calculate("MACD", SYMBOL, TIMEFRAME, candles, parameters=params)

    macd = result.values["macd"]
    signal = result.values["signal"]
    hist = result.values["histogram"]

    # Independently compute fast/slow EMA via the engine's EMA indicator.
    fast_res = engine.calculate("EMA", SYMBOL, TIMEFRAME, candles,
                                parameters=IndicatorParameters(
                                    values={"periods": [5]}))
    slow_res = engine.calculate("EMA", SYMBOL, TIMEFRAME, candles,
                                parameters=IndicatorParameters(
                                    values={"periods": [12]}))
    fast_ema = fast_res.values["ema_5"]
    slow_ema = slow_res.values["ema_12"]

    for i in range(len(closes)):
        f = fast_ema[i]
        s = slow_ema[i]
        m = macd[i]
        if f is None or s is None:
            assert m is None, f"index {i}: expected None macd, got {m}"
        else:
            assert m is not None
            assert abs(m - (f - s)) < Decimal("0.001"), f"index {i}: {m} != {f}-{s}"
        # histogram
        if m is not None and signal[i] is not None:
            assert hist[i] is not None
            assert abs(hist[i] - (m - signal[i])) < Decimal("0.001")
        else:
            assert hist[i] is None


def test_macd_fast_must_be_less_than_slow(engine):
    params = IndicatorParameters(
        values={"fast_period": 20, "slow_period": 10, "signal_period": 3}
    )
    ind = engine.registry.get("MACD")
    with pytest.raises(ValueError):
        ind.validate_parameters(params)


def test_macd_constant_price(engine):
    candles = make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                             Decimal("100"), 100) for _ in range(40)])
    result = engine.calculate("MACD", SYMBOL, TIMEFRAME, candles)
    # Constant price → all EMAs equal → MACD = 0, signal = 0, hist = 0.
    vals = [v for v in result.values["macd"] if v is not None]
    assert all(v == Decimal(0) for v in vals)
    sig_vals = [v for v in result.values["signal"] if v is not None]
    assert all(v == Decimal(0) for v in sig_vals)
