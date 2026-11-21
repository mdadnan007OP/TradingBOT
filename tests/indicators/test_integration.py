"""Integration tests for the Technical Indicator Engine.

Verifies the complete data flow:
    Market Data Engine → validated OHLC candles → Indicator Engine → results.

Also verifies that the same indicator formulas produce equivalent results for
equivalent candle inputs regardless of source (mock / CSV / MT5-originated).
No MT5 terminal connection is required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from tests.indicators.conftest import make_candles

SYMBOL = "EURUSD"
TIMEFRAME = MarketTimeframe.M1


def _make_candle_list(values):
    return make_candles([(Decimal(str(v)), Decimal(str(v)), Decimal(str(v)),
                          Decimal(str(v)), 100) for v in values])


@pytest.fixture
def engine():
    return create_engine()


def test_indicator_results_source_agnostic(engine):
    # Same candle inputs → identical indicator results regardless of provenance.
    candles_sim = _make_candle_list(range(10, 31))
    candles_hist = _make_candle_list(range(10, 31))
    # Tag historical candles as HISTORICAL provenance.
    for c in candles_hist:
        # OHLCBar is frozen; rebuild with HISTORICAL source.
        from dataclasses import replace
        candles_hist[candles_hist.index(c)] = replace(c, data_source=DataSource.HISTORICAL)

    r_sim = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles_sim,
                             data_source=DataSource.SIMULATED)
    r_hist = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles_hist,
                              data_source=DataSource.HISTORICAL)
    assert r_sim.values["sma_20"] == r_hist.values["sma_20"]
    assert r_sim.readiness == r_hist.readiness
    assert r_sim.data_source == DataSource.SIMULATED
    assert r_hist.data_source == DataSource.HISTORICAL


def test_warmup_no_look_ahead(engine):
    # Insufficient data → None values, never manufactured future values.
    candles = _make_candle_list(range(10, 15))  # 5 candles, SMA(200) needs 200
    result = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles)
    assert all(v is None for v in result.values["sma_200"])
    assert result.readiness.value in ("insufficient", "warming_up")


def test_completed_candles_by_default(engine):
    # Incomplete candles are dropped unless explicitly allowed.
    from src.market_data.models import DataSource
    complete = OHLCBar(symbol=SYMBOL, timeframe=TIMEFRAME,
                       timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                       open=Decimal("10"), high=Decimal("10"), low=Decimal("10"),
                       close=Decimal("10"), tick_volume=1, real_volume=1,
                       is_complete=True, data_source=DataSource.SIMULATED)
    incomplete = OHLCBar(symbol=SYMBOL, timeframe=TIMEFRAME,
                         timestamp=datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc),
                         open=Decimal("10"), high=Decimal("10"), low=Decimal("10"),
                         close=Decimal("10"), tick_volume=1, real_volume=1,
                         is_complete=False, data_source=DataSource.SIMULATED)
    result = engine.calculate("SMA", SYMBOL, TIMEFRAME, [complete, incomplete])
    assert result.bar_count == 1  # incomplete dropped


def test_indicator_available_to_strategy_layer(engine):
    # Results expose last_value for downstream strategy consumption.
    candles = _make_candle_list(range(10, 31))
    result = engine.calculate("RSI", SYMBOL, TIMEFRAME, candles)
    assert result.last_value("rsi") is not None
    assert result.warmup_periods == 14
    assert result.metadata["period"] == 14
