"""Shared test helpers for indicator tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Sequence, Tuple

from src.market_data.models import (
    DataSource,
    MarketTimeframe,
    OHLCBar,
)


def make_candles(
    ohlcv: Sequence[Tuple[Decimal, Decimal, Decimal, Decimal, int]],
    symbol: str = "EURUSD",
    timeframe: MarketTimeframe = MarketTimeframe.M1,
    start: datetime = None,
    data_source: DataSource = DataSource.SIMULATED,
    is_complete: bool = True,
) -> List[OHLCBar]:
    """Build OHLCBar candles from (open, high, low, close, volume) tuples."""
    if start is None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles: List[OHLCBar] = []
    for i, (o, h, l, c, v) in enumerate(ohlcv):
        candles.append(
            OHLCBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=start + timedelta(minutes=i),
                open=o,
                high=h,
                low=l,
                close=c,
                tick_volume=v,
                real_volume=v,
                is_complete=is_complete,
                data_source=data_source,
            )
        )
    return candles


def last_non_none(series: Sequence) -> object:
    """Return the last non-None element of a series, or None."""
    for v in reversed(series):
        if v is not None:
            return v
    return None


def count_none(series: Sequence) -> int:
    return sum(1 for v in series if v is None)
