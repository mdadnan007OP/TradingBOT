"""Shared test helpers for strategy tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List

from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.base import SignalDirection, SignalStatus


def make_candles(
    closes: List[Decimal],
    symbol: str = "EURUSD",
    timeframe: MarketTimeframe = MarketTimeframe.H1,
    start: datetime = None,
    data_source: DataSource = DataSource.SIMULATED,
    is_complete: bool = True,
) -> List[OHLCBar]:
    """Build OHLCBar candles from a list of close prices.

    Creates realistic OHLC data where high/low/close are derived from the
    close price with a small range.
    """
    if start is None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    candles: List[OHLCBar] = []
    for i, close in enumerate(closes):
        close_d = Decimal(str(close))
        # Create a small range around the close
        rng = close_d * Decimal("0.001")  # 0.1% range
        open_p = close_d - (rng * Decimal("0.3"))
        high_p = close_d + rng
        low_p = close_d - rng
        # Ensure OHLC validity
        if high_p < max(open_p, close_d):
            high_p = max(open_p, close_d) + Decimal("0.0001")
        if low_p > min(open_p, close_d):
            low_p = min(open_p, close_d) - Decimal("0.0001")

        candles.append(
            OHLCBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=start + timedelta(hours=i),
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_d,
                tick_volume=100,
                real_volume=100,
                is_complete=is_complete,
                data_source=data_source,
            )
        )
    return candles


def make_trending_candles(
    n: int = 50,
    start_price: Decimal = Decimal("100"),
    step: Decimal = Decimal("1"),
    symbol: str = "EURUSD",
    timeframe: MarketTimeframe = MarketTimeframe.H1,
) -> List[OHLCBar]:
    """Create strongly trending upward candles."""
    closes = [start_price + (step * i) for i in range(n)]
    return make_candles(closes, symbol=symbol, timeframe=timeframe)


def make_ranging_candles(
    n: int = 50,
    center: Decimal = Decimal("100"),
    amplitude: Decimal = Decimal("5"),
    symbol: str = "EURUSD",
    timeframe: MarketTimeframe = MarketTimeframe.H1,
) -> List[OHLCBar]:
    """Create ranging candles oscillating around a center price."""
    import math

    closes = []
    for i in range(n):
        # Oscillate using sine wave
        offset = amplitude * Decimal(str(math.sin(i * 0.2)))
        closes.append(center + offset)
    return make_candles(closes, symbol=symbol, timeframe=timeframe)


def make_downtrending_candles(
    n: int = 50,
    start_price: Decimal = Decimal("100"),
    step: Decimal = Decimal("1"),
    symbol: str = "EURUSD",
    timeframe: MarketTimeframe = MarketTimeframe.H1,
) -> List[OHLCBar]:
    """Create strongly trending downward candles."""
    closes = [start_price - (step * i) for i in range(n)]
    return make_candles(closes, symbol=symbol, timeframe=timeframe)
