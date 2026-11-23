"""Event scheduler.

Builds the explicit chronological sequence of bar-arrival events across all
symbols/timeframes. Ordering is deterministic (by timestamp, then symbol, then
timeframe) and documented so multi-symbol/multi-timeframe backtests are
reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

from src.backtesting.data_loader import BacktestData
from src.market_data.models import MarketTimeframe, OHLCBar

SeriesKey = Tuple[str, MarketTimeframe]


@dataclass(frozen=True)
class BarEvent:
    """A single bar arrival at a point in the timeline."""

    timestamp: datetime
    symbol: str
    timeframe: MarketTimeframe
    bar: OHLCBar


class EventScheduler:
    """Produces the chronological sequence of bar-arrival events."""

    def __init__(self, data: BacktestData) -> None:
        self._by_time: Dict[datetime, List[BarEvent]] = {}
        for (symbol, tf), series in data.series.items():
            for bar in series.bars:
                self._by_time.setdefault(bar.timestamp, []).append(
                    BarEvent(bar.timestamp, symbol, tf, bar)
                )
        for ts in self._by_time:
            self._by_time[ts].sort(key=lambda e: (e.symbol, e.timeframe.value))

    def timestamps(self) -> List[datetime]:
        """Sorted unique timestamps across all series."""
        return sorted(self._by_time.keys())

    def bars_at(self, ts: datetime) -> List[BarEvent]:
        return list(self._by_time.get(ts, []))

    def total_events(self) -> int:
        return sum(len(v) for v in self._by_time.values())

    def __len__(self) -> int:
        return len(self._by_time)