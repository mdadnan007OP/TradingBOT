"""Historical CSV market data provider.

Loads OHLC candles from local CSV files. Required columns:
    timestamp, open, high, low, close
Optional columns:
    tick_volume, real_volume, spread, bid, ask, is_complete

Malformed files and invalid records are handled gracefully. Missing prices are
never invented -- invalid rows are skipped and reported.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional

from src.market_data.base import MarketDataProvider
from src.market_data.models import (
    DataSource,
    DEFAULT_SYMBOLS,
    DEFAULT_INSTRUMENT_SPECS,
    InstrumentSpec,
    MarketQuote,
    MarketSymbol,
    MarketTimeframe,
    OHLCBar,
)

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close"}
OPTIONAL_COLUMNS = {
    "tick_volume",
    "real_volume",
    "spread",
    "bid",
    "ask",
    "is_complete",
    "data_source",
}


class HistoricalCSVProvider(MarketDataProvider):
    """Loads historical OHLC bars from CSV files on disk.

    Each CSV file should contain one symbol/timeframe combination. The file
    naming convention is ``{SYMBOL}_{TIMEFRAME}.csv`` (e.g. ``EURUSD_M1.csv``),
    but the symbol and timeframe can also be overridden via constructor
    arguments.
    """

    def __init__(
        self,
        data_dir: str = "data/historical",
        symbol: Optional[str] = None,
        timeframe: Optional[MarketTimeframe] = None,
        instrument_specs: Optional[Dict[str, InstrumentSpec]] = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._symbol = symbol
        self._timeframe = timeframe
        self._connected = False
        self._instrument_specs: Dict[str, InstrumentSpec] = (
            instrument_specs or {}
        )
        if not self._instrument_specs:
            self._instrument_specs = {
                s.canonical_symbol: s for s in DEFAULT_INSTRUMENT_SPECS
            }
        self._bars_cache: Dict[tuple[str, MarketTimeframe], List[OHLCBar]] = {}

    @property
    def name(self) -> str:
        return f"HistoricalCSVProvider ({self._data_dir})"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_simulated(self) -> bool:
        return False

    def connect(self) -> bool:
        if not self._data_dir.exists():
            logger.warning(
                "CSV data directory does not exist: %s", self._data_dir
            )
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        self._bars_cache.clear()
        return True

    def get_symbols(self) -> List[MarketSymbol]:
        if self._symbol:
            return [self._resolve_symbol(self._symbol)]
        specs = list(self._instrument_specs.values())
        return [
            MarketSymbol(
                symbol=s.canonical_symbol,
                name=s.name,
                instrument_type=s.instrument_type,
                base_currency=s.base_currency,
                quote_currency=s.quote_currency,
            )
            for s in specs
        ]

    def get_timeframes(self) -> List[MarketTimeframe]:
        if self._timeframe:
            return [self._timeframe]
        return list(MarketTimeframe)

    def spec_for_symbol(self, symbol: str) -> Optional[InstrumentSpec]:
        return self._instrument_specs.get(symbol)

    def _resolve_symbol(self, symbol: str) -> MarketSymbol:
        spec = self.spec_for_symbol(symbol)
        if spec is not None:
            return MarketSymbol(
                symbol=spec.canonical_symbol,
                name=spec.name,
                instrument_type=spec.instrument_type,
                base_currency=spec.base_currency,
                quote_currency=spec.quote_currency,
            )
        for s in DEFAULT_SYMBOLS:
            if s.symbol == symbol:
                return s
        return MarketSymbol(symbol=symbol, name=symbol)

    def _parse_timestamp(self, raw: str) -> Optional[datetime]:
        """Parse a timestamp string into a timezone-aware UTC datetime."""
        raw = raw.strip()
        if not raw:
            return None
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(raw, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except ValueError:
                continue
        logger.warning("Could not parse timestamp: %s", raw)
        return None

    def _parse_decimal(self, raw: str) -> Optional[Decimal]:
        raw = raw.strip()
        if not raw:
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            logger.warning("Could not parse decimal: %s", raw)
            return None

    def _parse_int(self, raw: str) -> Optional[int]:
        raw = raw.strip()
        if not raw:
            return None
        try:
            return int(float(raw))
        except (ValueError, TypeError):
            logger.warning("Could not parse integer: %s", raw)
            return None

    def _parse_bool(self, raw: str) -> bool:
        raw = raw.strip().lower()
        return raw in ("true", "1", "yes", "on")

    def _parse_data_source(self, raw: str) -> DataSource:
        raw = raw.strip().lower()
        if raw in ("historical", "real", "live"):
            return DataSource.HISTORICAL
        if raw in ("simulated", "sim", "mock"):
            return DataSource.SIMULATED
        return DataSource.HISTORICAL

    def _load_file(self, filepath: Path) -> List[OHLCBar]:
        """Load OHLC bars from a single CSV file."""
        bars: List[OHLCBar] = []
        try:
            with open(filepath, "r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None:
                    logger.warning("CSV file has no header: %s", filepath)
                    return bars

                header_set = set(reader.fieldnames)
                missing = REQUIRED_COLUMNS - header_set
                if missing:
                    logger.warning(
                        "CSV file missing required columns %s: %s",
                        missing,
                        filepath,
                    )
                    return bars

                parts = filepath.stem.split("_")
                file_symbol = parts[0] if parts else filepath.stem
                try:
                    file_tf = MarketTimeframe.from_string(parts[1])
                except (ValueError, IndexError):
                    file_tf = MarketTimeframe.M1

                for row_num, row in enumerate(reader, start=2):
                    try:
                        ts = self._parse_timestamp(row.get("timestamp", ""))
                        if ts is None:
                            logger.warning(
                                "Invalid timestamp at row %d in %s", row_num, filepath
                            )
                            continue

                        open_val = self._parse_decimal(row.get("open", ""))
                        high_val = self._parse_decimal(row.get("high", ""))
                        low_val = self._parse_decimal(row.get("low", ""))
                        close_val = self._parse_decimal(row.get("close", ""))

                        if any(
                            v is None
                            for v in (open_val, high_val, low_val, close_val)
                        ):
                            logger.warning(
                                "Invalid OHLC values at row %d in %s",
                                row_num,
                                filepath,
                            )
                            continue

                        tick_vol = (
                            self._parse_int(row.get("tick_volume", ""))
                            if "tick_volume" in header_set
                            else None
                        )
                        real_vol = (
                            self._parse_int(row.get("real_volume", ""))
                            if "real_volume" in header_set
                            else None
                        )
                        spread = (
                            self._parse_decimal(row.get("spread", ""))
                            if "spread" in header_set
                            else None
                        )
                        bid = (
                            self._parse_decimal(row.get("bid", ""))
                            if "bid" in header_set
                            else None
                        )
                        ask = (
                            self._parse_decimal(row.get("ask", ""))
                            if "ask" in header_set
                            else None
                        )
                        is_complete = self._parse_bool(
                            row.get("is_complete", "true")
                        )
                        if "is_complete" not in header_set:
                            is_complete = True
                        data_source = self._parse_data_source(
                            row.get("data_source", "historical")
                        )
                        if "data_source" not in header_set:
                            data_source = DataSource.HISTORICAL

                        bar = OHLCBar(
                            symbol=file_symbol,
                            timeframe=file_tf,
                            timestamp=ts,
                            open=open_val,
                            high=high_val,
                            low=low_val,
                            close=close_val,
                            tick_volume=tick_vol,
                            real_volume=real_vol,
                            spread=spread,
                            bid=bid,
                            ask=ask,
                            is_complete=is_complete,
                            timestamp_convention="bar_open",
                            data_source=data_source,
                        )
                        bars.append(bar)
                    except Exception as exc:  # noqa: BLE001 - skip bad rows
                        logger.warning(
                            "Skipping row %d in %s: %s", row_num, filepath, exc
                        )
        except OSError as exc:
            logger.warning("Could not read CSV file %s: %s", filepath, exc)
        return bars

    def _discover_files(
        self,
    ) -> Dict[tuple[str, MarketTimeframe], Path]:
        """Scan the data directory for CSV files matching {SYMBOL}_{TIMEFRAME}.csv."""
        found: Dict[tuple[str, MarketTimeframe], Path] = {}
        if not self._data_dir.exists():
            return found
        for filepath in self._data_dir.glob("*.csv"):
            parts = filepath.stem.split("_")
            if len(parts) < 2:
                continue
            symbol = parts[0]
            try:
                tf = MarketTimeframe.from_string(parts[1])
            except ValueError:
                continue
            found[(symbol, tf)] = filepath
        return found

    def get_candles(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
    ) -> List[OHLCBar]:
        if not self._connected:
            logger.warning("get_candles called while disconnected")
            return []

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        key = (symbol, timeframe)
        if key not in self._bars_cache:
            files = self._discover_files()
            filepath = files.get(key)
            if filepath is None:
                logger.warning(
                    "No CSV file found for %s %s", symbol, timeframe.value
                )
                self._bars_cache[key] = []
            else:
                self._bars_cache[key] = self._load_file(filepath)

        bars = self._bars_cache[key]
        return [b for b in bars if start_time <= b.timestamp <= end_time]

    def get_latest_candle(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
    ) -> Optional[OHLCBar]:
        bars = self.get_candles(
            symbol,
            timeframe,
            datetime.min.replace(tzinfo=timezone.utc),
            datetime.max.replace(tzinfo=timezone.utc),
        )
        if not bars:
            return None
        return max(bars, key=lambda b: b.timestamp)

    def get_quote(self, symbol: str) -> Optional[MarketQuote]:
        # CSV provider is historical only; no live quotes.
        return None
