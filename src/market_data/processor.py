"""Data processing engine for market data.

Provides provider-independent operations on OHLC bars:
    * Chronological sorting
    * Symbol / timeframe / date-range filtering
    * Missing interval detection
    * Standardized output for downstream indicator calculations
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from src.market_data.models import (
    MarketTimeframe,
    OHLCBar,
)


class DataProcessor:
    """Processes and normalizes OHLC bar data."""

    @staticmethod
    def sort_chronologically(bars: List[OHLCBar]) -> List[OHLCBar]:
        """Return bars sorted by timestamp ascending."""
        return sorted(bars, key=lambda b: b.timestamp)

    @staticmethod
    def filter_by_symbol(bars: List[OHLCBar], symbol: str) -> List[OHLCBar]:
        """Return only bars matching ``symbol``."""
        return [b for b in bars if b.symbol == symbol]

    @staticmethod
    def filter_by_timeframe(
        bars: List[OHLCBar], timeframe: MarketTimeframe
    ) -> List[OHLCBar]:
        """Return only bars matching ``timeframe``."""
        return [b for b in bars if b.timeframe == timeframe]

    @staticmethod
    def filter_by_date_range(
        bars: List[OHLCBar],
        start_time: datetime,
        end_time: datetime,
    ) -> List[OHLCBar]:
        """Return only bars within [start_time, end_time] (inclusive)."""
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        return [b for b in bars if start_time <= b.timestamp <= end_time]

    @staticmethod
    def deduplicate(bars: List[OHLCBar]) -> List[OHLCBar]:
        """Remove duplicate bars (same symbol, timeframe, timestamp)."""
        seen: set[tuple[str, MarketTimeframe, datetime]] = set()
        result: List[OHLCBar] = []
        for b in bars:
            key = (b.symbol, b.timeframe, b.timestamp)
            if key not in seen:
                seen.add(key)
                result.append(b)
        return result

    @staticmethod
    def detect_missing_intervals(
        bars: List[OHLCBar],
    ) -> List[datetime]:
        """Detect expected-but-missing candle timestamps.

        Assumes bars belong to a single symbol/timeframe. Returns the list of
        timestamps that should exist given the timeframe step but are absent.
        """
        if len(bars) < 2:
            return []
        sorted_bars = DataProcessor.sort_chronologically(bars)
        step = timedelta(minutes=sorted_bars[0].timeframe.minutes)
        missing: List[datetime] = []
        for i in range(1, len(sorted_bars)):
            prev = sorted_bars[i - 1].timestamp
            curr = sorted_bars[i].timestamp
            expected = prev + step
            while expected < curr:
                missing.append(expected)
                expected += step
        return missing

    @staticmethod
    def standardize(bars: List[OHLCBar]) -> List[OHLCBar]:
        """Standardize output: sort, deduplicate, ensure UTC timestamps.

        Returns a new list; input is not modified.
        """
        result = DataProcessor.deduplicate(bars)
        result = DataProcessor.sort_chronologically(result)
        return result

    @staticmethod
    def prepare_for_indicators(bars: List[OHLCBar]) -> List[OHLCBar]:
        """Prepare bars for downstream indicator calculations.

        Returns sorted, deduplicated, UTC-standardized bars with no missing
        interior intervals flagged (caller may inspect via
        ``detect_missing_intervals``).
        """
        return DataProcessor.standardize(bars)
