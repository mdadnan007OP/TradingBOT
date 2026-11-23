"""Historical data loading and validation for backtests.

Loads OHLC candles from in-memory lists or local CSV files (via the existing
Phase 2 ``HistoricalCSVProvider``), validates them, and preserves missing-data
information rather than fabricating prices. Supports multiple symbols and
timeframes in a single backtest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from src.backtesting.config import DataConfig
from src.market_data.models import (
    DataSource,
    InstrumentSpec,
    MarketTimeframe,
    OHLCBar,
    spec_for_symbol,
)
from src.market_data.processor import DataProcessor

logger = logging.getLogger(__name__)

SeriesKey = Tuple[str, MarketTimeframe]


@dataclass
class SeriesData:
    """Validated candle series for one (symbol, timeframe)."""

    symbol: str
    timeframe: MarketTimeframe
    bars: List[OHLCBar]
    missing_timestamps: List[datetime] = field(default_factory=list)
    dropped_incomplete: int = 0
    dropped_duplicates: int = 0
    invalid_rows: int = 0
    data_source: DataSource = DataSource.HISTORICAL
    warnings: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.bars


@dataclass
class BacktestData:
    """All validated series for a backtest, keyed by (symbol, timeframe)."""

    series: Dict[SeriesKey, SeriesData] = field(default_factory=dict)

    def get(self, symbol: str, timeframe: MarketTimeframe) -> Optional[SeriesData]:
        return self.series.get((symbol, timeframe))

    def symbols(self) -> List[str]:
        return sorted({s for (s, _) in self.series})

    def timeframes(self) -> List[MarketTimeframe]:
        seen: Dict[MarketTimeframe, None] = {}
        for (_, tf) in self.series:
            seen[tf] = None
        return list(seen)

    def timeframes_for(self, symbol: str) -> List[MarketTimeframe]:
        return [tf for (s, tf) in self.series if s == symbol]

    def all_timestamps(self) -> List[datetime]:
        stamps = set()
        for data in self.series.values():
            for bar in data.bars:
                stamps.add(bar.timestamp)
        return sorted(stamps)

    def global_start(self) -> Optional[datetime]:
        stamps = self.all_timestamps()
        return stamps[0] if stamps else None

    def global_end(self) -> Optional[datetime]:
        stamps = self.all_timestamps()
        return stamps[-1] if stamps else None


class BacktestDataLoader:
    """Loads and validates historical candles for backtesting."""

    def __init__(self, config: Optional[DataConfig] = None) -> None:
        self.config = config or DataConfig()
        self._processor = DataProcessor()

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_series(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        bars: List[OHLCBar],
    ) -> SeriesData:
        warnings: List[str] = []
        dropped_incomplete = 0
        invalid_rows = 0
        dropped_duplicates = 0
        data_source = DataSource.HISTORICAL

        cleaned: List[OHLCBar] = []
        for bar in bars:
            if not isinstance(bar.timestamp, datetime) or bar.timestamp.tzinfo is None:
                invalid_rows += 1
                continue
            if self.config.validate_ohlc:
                if bar.high < bar.low or bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
                    invalid_rows += 1
                    continue
            if not bar.is_complete:
                dropped_incomplete += 1
                continue
            cleaned.append(bar)

        # Deduplicate + sort using the existing processor.
        if self.config.drop_duplicate_timestamps:
            before = len(cleaned)
            cleaned = self._processor.standardize(cleaned)
            dropped_duplicates = before - len(cleaned)
        else:
            cleaned = sorted(cleaned, key=lambda b: b.timestamp)

        if cleaned:
            data_source = cleaned[-1].data_source

        missing: List[datetime] = []
        if self.config.validate_timestamps and len(cleaned) >= 2:
            missing = self._processor.detect_missing_intervals(cleaned)

        if invalid_rows:
            warnings.append(f"{invalid_rows} invalid rows skipped")
        if dropped_incomplete:
            warnings.append(f"{dropped_incomplete} incomplete candles excluded")
        if dropped_duplicates:
            warnings.append(f"{dropped_duplicates} duplicate timestamps removed")
        if missing:
            warnings.append(f"{len(missing)} missing intervals (not fabricated)")

        return SeriesData(
            symbol=symbol,
            timeframe=timeframe,
            bars=cleaned,
            missing_timestamps=missing,
            dropped_incomplete=dropped_incomplete,
            dropped_duplicates=dropped_duplicates,
            invalid_rows=invalid_rows,
            data_source=data_source,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Public loaders
    # ------------------------------------------------------------------

    def from_lists(
        self,
        data: Dict[SeriesKey, List[OHLCBar]],
    ) -> BacktestData:
        """Build a BacktestData from in-memory candle lists."""
        result = BacktestData()
        for (symbol, timeframe), bars in data.items():
            result.series[(symbol, timeframe)] = self._validate_series(
                symbol, timeframe, bars
            )
        return result

    def from_csv_dir(
        self,
        data_dir: str,
        symbols: List[str],
        timeframes: List[MarketTimeframe],
    ) -> BacktestData:
        """Load candles from CSV files via the Phase 2 HistoricalCSVProvider."""
        from src.market_data.csv_provider import HistoricalCSVProvider

        provider = HistoricalCSVProvider(data_dir=data_dir)
        provider.connect()
        data: Dict[SeriesKey, List[OHLCBar]] = {}
        start = datetime.min.replace(tzinfo=timezone.utc)
        end = datetime.max.replace(tzinfo=timezone.utc)
        try:
            for symbol in symbols:
                for tf in timeframes:
                    bars = provider.get_candles(symbol, tf, start, end)
                    data[(symbol, tf)] = bars
        finally:
            provider.disconnect()
        return self.from_lists(data)

    def spec_for(self, symbol: str) -> Optional[InstrumentSpec]:
        return spec_for_symbol(symbol)