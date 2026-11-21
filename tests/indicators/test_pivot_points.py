"""Unit tests for Classic Pivot Points indicator."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.indicators.base import IndicatorParameters
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar

SYMBOL = "EURUSD"
TIMEFRAME = MarketTimeframe.H1


@pytest.fixture
def engine():
    return create_engine()


def _bar(day, hour, h, l, c):
    return OHLCBar(symbol=SYMBOL, timeframe=TIMEFRAME,
                   timestamp=datetime(2024, 1, day, hour, tzinfo=timezone.utc),
                   open=Decimal(str(h)), high=Decimal(str(h)),
                   low=Decimal(str(l)), close=Decimal(str(c)),
                   tick_volume=100, real_volume=100, is_complete=True,
                   data_source=DataSource.SIMULATED)


def test_pivot_exact_values(engine):
    # Day 1: H=110, L=100, C=105. Day 2 pivot computed from Day 1.
    # PP=105, R1=110, S1=100, R2=115, S2=95, R3=120, S3=90.
    candles = [
        _bar(1, 0, 110, 100, 105),
        _bar(1, 1, 110, 100, 105),
        _bar(2, 0, 110, 100, 105),  # day 2 → uses day 1 HLC
        _bar(2, 1, 110, 100, 105),
    ]
    result = engine.calculate("Classic Pivot Points", SYMBOL, TIMEFRAME, candles)
    # Day 1 candles → None (no previous period).
    assert result.values["pivot"][0] is None
    assert result.values["r1"][0] is None
    # Day 2 candles → pivot from Day 1.
    assert result.values["pivot"][2] == Decimal(105)
    assert result.values["r1"][2] == Decimal(110)
    assert result.values["s1"][2] == Decimal(100)
    assert result.values["r2"][2] == Decimal(115)
    assert result.values["s2"][2] == Decimal(95)
    assert result.values["r3"][2] == Decimal(120)
    assert result.values["s3"][2] == Decimal(90)


def test_pivot_no_lookahead(engine):
    # Day 2's pivot must NOT reflect Day 2's own HLC.
    # Day 1: H=100,L=90,C=95 → PP=95.
    # Day 2: H=200,L=100,C=150 (wild) → pivot still from Day 1 = 95.
    candles = [
        _bar(1, 0, 100, 90, 95),
        _bar(2, 0, 200, 100, 150),
    ]
    result = engine.calculate("Classic Pivot Points", SYMBOL, TIMEFRAME, candles)
    assert result.values["pivot"][1] == Decimal(95), f"Look-ahead detected: {result.values['pivot'][1]}"


def test_pivot_weekly_granularity(engine):
    candles = [
        _bar(1, 0, 110, 100, 105),   # Monday week 1
        _bar(8, 0, 110, 100, 105),   # Monday week 2 → uses week 1 HLC
    ]
    result = engine.calculate("Classic Pivot Points", SYMBOL, TIMEFRAME, candles,
                              parameters=IndicatorParameters(
                                  values={"granularity": "weekly"}))
    assert result.values["pivot"][0] is None
    assert result.values["pivot"][1] == Decimal(105)


def test_pivot_insufficient(engine):
    candles = [_bar(1, 0, 110, 100, 105)]
    result = engine.calculate("Classic Pivot Points", SYMBOL, TIMEFRAME, candles)
    assert result.readiness.value == "insufficient"
    assert all(v is None for v in result.values["pivot"])
