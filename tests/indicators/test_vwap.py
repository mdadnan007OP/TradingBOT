"""Unit tests for VWAP indicator."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.indicators.base import IndicatorParameters
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from tests.indicators.conftest import make_candles

SYMBOL = "EURUSD"
TIMEFRAME = MarketTimeframe.M1


@pytest.fixture
def engine():
    return create_engine()


def test_vwap_exact_value(engine):
    # bar0: tp=(10+9+10)/3=29/3, vol=100 → tp*vol=2900/3
    # bar1: tp=(11+10+11)/3=32/3, vol=200 → tp*vol=6400/3
    # cum: tp*vol=9300/3=3100, vol=300 → vwap=3100/300=10.333...
    def bar(ts, h, l, c, vol):
        return OHLCBar(symbol=SYMBOL, timeframe=TIMEFRAME, timestamp=ts,
                       open=Decimal(str(h)), high=Decimal(str(h)),
                       low=Decimal(str(l)), close=Decimal(str(c)),
                       tick_volume=vol, real_volume=vol, is_complete=True,
                       data_source=DataSource.SIMULATED)
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = [bar(base, 10, 9, 10, 100),
               bar(base.replace(minute=1), 11, 10, 11, 200)]
    result = engine.calculate("VWAP", SYMBOL, TIMEFRAME, candles)
    assert result.values["vwap"][1] is not None
    expected = Decimal(3100) / Decimal(300)
    assert abs(result.values["vwap"][1] - expected) < Decimal("0.01")
    assert result.metadata["volume_basis_per_bar"][1] == "real"


def test_vwap_session_reset_daily(engine):
    # Bars on two different UTC days → VWAP resets at day 2.
    def bar(day, minute, h, l, c, vol):
        return OHLCBar(symbol=SYMBOL, timeframe=TIMEFRAME,
                       timestamp=datetime(2024, 1, day, 0, minute, tzinfo=timezone.utc),
                       open=Decimal(str(h)), high=Decimal(str(h)),
                       low=Decimal(str(l)), close=Decimal(str(c)),
                       tick_volume=vol, real_volume=vol, is_complete=True,
                       data_source=DataSource.SIMULATED)
    candles = [
        bar(1, 0, 10, 9, 10, 100),
        bar(1, 1, 10, 9, 10, 100),
        bar(2, 0, 10, 9, 10, 100),  # new day → reset
    ]
    result = engine.calculate("VWAP", SYMBOL, TIMEFRAME, candles,
                              parameters=IndicatorParameters(
                                  values={"volume_source": "real", "session_reset": "daily"}))
    # day 2 bar: only its own volume counts → vwap = tp = 9.666...
    assert result.values["vwap"][2] is not None
    expected = Decimal(29) / Decimal(3)
    assert abs(result.values["vwap"][2] - expected) < Decimal("0.01")


def test_vwap_volume_basis_tick(engine):
    # Only tick_volume → basis "tick", labeled in metadata warning.
    def bar(h, l, c, tick_vol, real_vol):
        return OHLCBar(symbol=SYMBOL, timeframe=TIMEFRAME,
                       timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                       open=Decimal(str(h)), high=Decimal(str(h)),
                       low=Decimal(str(l)), close=Decimal(str(c)),
                       tick_volume=tick_vol, real_volume=real_vol,
                       is_complete=True, data_source=DataSource.SIMULATED)
    candles = [bar(10, 9, 10, 100, None)]
    result = engine.calculate("VWAP", SYMBOL, TIMEFRAME, candles,
                              parameters=IndicatorParameters(
                                  values={"volume_source": "tick"}))
    assert result.metadata["volume_basis_per_bar"][0] == "tick"
    assert "tick volume" in result.metadata["tick_volume_warning"].lower()


def test_vwap_unavailable_without_volume(engine):
    # volume_source=real but no real_volume → vwap None.
    def bar(h, l, c, tick_vol, real_vol):
        return OHLCBar(symbol=SYMBOL, timeframe=TIMEFRAME,
                       timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                       open=Decimal(str(h)), high=Decimal(str(h)),
                       low=Decimal(str(l)), close=Decimal(str(c)),
                       tick_volume=tick_vol, real_volume=real_vol,
                       is_complete=True, data_source=DataSource.SIMULATED)
    candles = [bar(10, 9, 10, 100, None)]
    result = engine.calculate("VWAP", SYMBOL, TIMEFRAME, candles,
                              parameters=IndicatorParameters(
                                  values={"volume_source": "real"}))
    assert result.values["vwap"][0] is None
    assert result.readiness.value == "insufficient"
