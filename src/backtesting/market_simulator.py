"""Market simulator.

Reveals historical candles chronologically and exposes the "known so far" window
per series. This is the core look-ahead-prevention mechanism: callers can only
ever see bars whose timestamp has already been revealed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.backtesting.data_loader import BacktestData, SeriesData
from src.market_data.models import MarketTimeframe, OHLCBar

SeriesKey = Tuple[str, MarketTimeframe]


class MarketSimulator:
    """Chronological market-data replayer with per-series cursors."""

    def __init__(self, data: BacktestData) -> None:
        self._data = data
        self._cursors: Dict[SeriesKey, int] = {key: 0 for key in data.series}

    def series_keys(self) -> List[SeriesKey]:
        return list(self._data.series.keys())

    def series(self, symbol: str, timeframe: MarketTimeframe) -> Optional[SeriesData]:
        return self._data.get(symbol, timeframe)

    def reveal_through(self, now: datetime) -> None:
        """Advance every series cursor to include all bars with ts <= now."""
        for key, series in self._data.series.items():
            cursor = self._cursors[key]
            bars = series.bars
            while cursor < len(bars) and bars[cursor].timestamp <= now:
                cursor += 1
            self._cursors[key] = cursor

    def window(self, symbol: str, timeframe: MarketTimeframe) -> List[OHLCBar]:
        """Return the revealed bars (ts <= now) for a series (copy)."""
        key = (symbol, timeframe)
        series = self._data.series.get(key)
        if series is None:
            return []
        cursor = self._cursors.get(key, 0)
        return list(series.bars[:cursor])

    def cursor(self, symbol: str, timeframe: MarketTimeframe) -> int:
        return self._cursors.get((symbol, timeframe), 0)

    def latest_bar(self, symbol: str, timeframe: MarketTimeframe) -> Optional[OHLCBar]:
        window = self.window(symbol, timeframe)
        return window[-1] if window else None

    def has_bar_at(self, symbol: str, timeframe: MarketTimeframe, ts: datetime) -> bool:
        series = self._data.series.get((symbol, timeframe))
        if series is None:
            return False
        idx = self._cursors.get((symbol, timeframe), 0) - 1
        return idx >= 0 and series.bars[idx].timestamp == ts

    def bar_at(self, symbol: str, timeframe: MarketTimeframe, ts: datetime) -> Optional[OHLCBar]:
        series = self._data.series.get((symbol, timeframe))
        if series is None:
            return None
        # Binary-ish search over revealed prefix.
        cursor = self._cursors.get((symbol, timeframe), 0)
        for i in range(cursor):
            if series.bars[i].timestamp == ts:
                return series.bars[i]
            if series.bars[i].timestamp > ts:
                break
        return None

    def primary_timeframe(self, symbol: str) -> Optional[MarketTimeframe]:
        """Return the first available timeframe for a symbol (lowest minutes)."""
        tfs = [tf for (s, tf) in self._data.series if s == symbol]
        if not tfs:
            return None
        return sorted(tfs, key=lambda t: t.minutes)[0]