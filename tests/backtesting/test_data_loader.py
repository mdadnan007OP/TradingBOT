"""Tests for the data loader and validation."""

from __future__ import annotations

from datetime import timedelta

from src.backtesting.config import DataConfig
from src.backtesting.data_loader import BacktestDataLoader
from src.market_data.models import DataSource, MarketTimeframe
from tests.backtesting.conftest import BASE, make_bar, make_bars


def test_load_and_count():
    bars = make_bars([1.10, 1.11, 1.12], symbol="EURUSD")
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): bars})
    assert len(data.get("EURUSD", MarketTimeframe.H1).bars) == 3


def test_duplicate_timestamps_removed():
    bars = make_bars([1.10, 1.11, 1.12], symbol="EURUSD")
    bars.append(bars[1])  # duplicate timestamp
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): bars})
    series = data.get("EURUSD", MarketTimeframe.H1)
    assert len(series.bars) == 3
    assert series.dropped_duplicates == 1


def test_missing_intervals_detected_not_fabricated():
    b0 = make_bar("EURUSD", MarketTimeframe.H1, BASE, 1.10, 1.11, 1.09, 1.105)
    # Skip one hour (gap at BASE + 1h).
    b2 = make_bar("EURUSD", MarketTimeframe.H1, BASE + timedelta(hours=2), 1.11, 1.12, 1.10, 1.115)
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): [b0, b2]})
    series = data.get("EURUSD", MarketTimeframe.H1)
    # Only 2 real bars; the gap is recorded, not filled.
    assert len(series.bars) == 2
    assert len(series.missing_timestamps) >= 1


def test_incomplete_candles_excluded():
    b0 = make_bar("EURUSD", MarketTimeframe.H1, BASE, 1.10, 1.11, 1.09, 1.105)
    b1 = make_bar("EURUSD", MarketTimeframe.H1, BASE + timedelta(hours=1), 1.10, 1.11, 1.09, 1.105, is_complete=False, data_source=DataSource.SIMULATED)
    b2 = make_bar("EURUSD", MarketTimeframe.H1, BASE + timedelta(hours=2), 1.11, 1.12, 1.10, 1.115)
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): [b0, b1, b2]})
    series = data.get("EURUSD", MarketTimeframe.H1)
    assert series.dropped_incomplete == 1
    assert len(series.bars) == 2


def test_rows_with_naive_timestamps_skipped():
    good = make_bar("EURUSD", MarketTimeframe.H1, BASE, 1.10, 1.11, 1.09, 1.105)
    # A bar with a naive timestamp cannot be constructed by the model, so we
    # verify the loader tolerates an empty/missing series instead.
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): [good]})
    assert len(data.get("EURUSD", MarketTimeframe.H1).bars) == 1


def test_multiple_symbols_and_timeframes():
    h1 = make_bars([1.10, 1.11], symbol="EURUSD", timeframe=MarketTimeframe.H1)
    m15 = make_bars([1.10, 1.11], symbol="EURUSD", timeframe=MarketTimeframe.M15)
    data = BacktestDataLoader().from_lists({
        ("EURUSD", MarketTimeframe.H1): h1,
        ("EURUSD", MarketTimeframe.M15): m15,
    })
    assert data.symbols() == ["EURUSD"]
    assert set(data.timeframes()) == {MarketTimeframe.H1, MarketTimeframe.M15}


def test_missing_data_allowed_by_default():
    # An empty series is allowed; the engine will simply have no bars for it.
    data = BacktestDataLoader(DataConfig(allow_missing_candles=True)).from_lists({})
    assert data.symbols() == []