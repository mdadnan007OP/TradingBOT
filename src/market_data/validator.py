"""Data validation engine for market data.

Validates OHLC bars for:
    * Positive prices
    * Correct OHLC relationships
    * Valid timezone-aware UTC timestamps
    * Duplicate timestamps
    * Out-of-order timestamps
    * Negative volume or spread
    * Missing candles / timeframe gaps (session-aware)
    * Unsupported symbols and timeframes
    * Incomplete candles treated as historical

Generates a ``DataQualityReport`` with errors and warnings. Never silently
manufactures missing market data. Market session awareness distinguishes
expected closures (e.g. Forex weekends) from unexpected data gaps.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

from src.market_data.models import (
    CandleCompletion,
    DataQualityReport,
    DataSource,
    DEFAULT_INSTRUMENT_SPECS,
    InstrumentSpec,
    MarketTimeframe,
    OHLCBar,
    ValidationIssue,
)
from src.market_data.sessions import DEFAULT_SESSIONS, SessionCalendar

logger = logging.getLogger(__name__)

# Default supported symbols derived from DEFAULT_INSTRUMENT_SPECS.
SUPPORTED_SYMBOLS = {
    s.canonical_symbol for s in DEFAULT_INSTRUMENT_SPECS
}
SUPPORTED_TIMEFRAMES = set(MarketTimeframe)


class DataValidator:
    """Validates collections of OHLC bars and produces quality reports.

    The validator can be made session-aware by passing a ``SessionCalendar``.
    When session-aware, gaps that coincide with expected market closures
    (weekends, daily breaks) are not reported as missing intervals.
    """

    def __init__(
        self,
        supported_symbols: Optional[Set[str]] = None,
        supported_timeframes: Optional[Set[MarketTimeframe]] = None,
        session_calendar: Optional[SessionCalendar] = None,
        instrument_specs: Optional[Dict[str, InstrumentSpec]] = None,
    ) -> None:
        self.supported_symbols = supported_symbols or SUPPORTED_SYMBOLS
        self.supported_timeframes = supported_timeframes or SUPPORTED_TIMEFRAMES
        self.session_calendar = session_calendar or SessionCalendar(DEFAULT_SESSIONS)
        self.instrument_specs = instrument_specs or {}

    # ------------------------------------------------------------------
    # Instrument spec helpers
    # ------------------------------------------------------------------

    def spec_for_symbol(self, symbol: str) -> Optional[InstrumentSpec]:
        """Return the ``InstrumentSpec`` for a symbol, or None."""
        return self.instrument_specs.get(symbol)

    def is_symbol_supported(self, symbol: str) -> bool:
        """Return True if the symbol is in the supported set or has a spec."""
        return symbol in self.supported_symbols or symbol in self.instrument_specs

    # ------------------------------------------------------------------
    # Session-aware gap detection
    # ------------------------------------------------------------------

    def _session_for_symbol(self, symbol: str) -> str:
        """Determine the session ID for a symbol."""
        spec = self.spec_for_symbol(symbol)
        if spec is not None and spec.market_session is not None:
            return spec.market_session
        return "forex"

    def _filter_expected_closures(
        self,
        session_id: str,
        missing: List[datetime],
        timeframe: MarketTimeframe,
    ) -> List[datetime]:
        """Remove missing intervals that fall within expected market closures."""
        if not missing:
            return missing
        session = self.session_calendar.get_session(session_id)
        if session is None:
            return missing
        real_missing: List[datetime] = []
        for ts in missing:
            if self.session_calendar.is_market_open(session_id, ts):
                real_missing.append(ts)
            else:
                logger.debug(
                    "Skipping expected closure at %s for session %s", ts, session_id
                )
        return real_missing

    # ------------------------------------------------------------------
    # Main validation
    # ------------------------------------------------------------------

    def validate_bars(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        bars: List[OHLCBar],
    ) -> DataQualityReport:
        """Validate a list of OHLC bars and return a quality report."""
        issues: List[ValidationIssue] = []
        valid_count = 0

        # Symbol/timeframe support checks.
        if symbol not in self.supported_symbols and symbol not in self.instrument_specs:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="UNSUPPORTED_SYMBOL",
                    message=f"Symbol {symbol} is not supported.",
                )
            )
        if timeframe not in self.supported_timeframes:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="UNSUPPORTED_TIMEFRAME",
                    message=f"Timeframe {timeframe.value} is not supported.",
                )
            )

        # Check for incomplete candles marked as historical.
        for bar in bars:
            if (
                bar.is_complete is False
                and bar.data_source == DataSource.HISTORICAL
            ):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="INCOMPLETE_HISTORICAL_CANDLE",
                        message=(
                            f"Historical candle at {bar.timestamp} is marked "
                            f"incomplete."
                        ),
                        timestamp=bar.timestamp,
                    )
                )

        total = len(bars)
        seen_timestamps: set[datetime] = set()
        prev_timestamp: Optional[datetime] = None
        expected_step = timedelta(minutes=timeframe.minutes)
        session_id = self._session_for_symbol(symbol)

        for bar in bars:
            bar_issues: List[ValidationIssue] = []

            # Positive prices.
            for name, value in (
                ("open", bar.open),
                ("high", bar.high),
                ("low", bar.low),
                ("close", bar.close),
            ):
                if value <= 0:
                    bar_issues.append(
                        ValidationIssue(
                            severity="error",
                            code="NON_POSITIVE_PRICE",
                            message=f"{name} price {value} is not positive.",
                            timestamp=bar.timestamp,
                        )
                    )

            # OHLC relationships.
            if bar.high < max(bar.open, bar.close):
                bar_issues.append(
                    ValidationIssue(
                        severity="error",
                        code="INVALID_OHLC",
                        message=(
                            f"High {bar.high} below max(open={bar.open}, "
                            f"close={bar.close})."
                        ),
                        timestamp=bar.timestamp,
                    )
                )
            if bar.low > min(bar.open, bar.close):
                bar_issues.append(
                    ValidationIssue(
                        severity="error",
                        code="INVALID_OHLC",
                        message=(
                            f"Low {bar.low} above min(open={bar.open}, "
                            f"close={bar.close})."
                        ),
                        timestamp=bar.timestamp,
                    )
                )
            if bar.high < bar.low:
                bar_issues.append(
                    ValidationIssue(
                        severity="error",
                        code="INVALID_OHLC",
                        message=f"High {bar.high} below low {bar.low}.",
                        timestamp=bar.timestamp,
                    )
                )

            # Timestamp timezone awareness.
            if bar.timestamp.tzinfo is None:
                bar_issues.append(
                    ValidationIssue(
                        severity="error",
                        code="NAIVE_TIMESTAMP",
                        message="Timestamp is not timezone-aware UTC.",
                        timestamp=bar.timestamp,
                    )
                )

            # Duplicate timestamps.
            if bar.timestamp in seen_timestamps:
                bar_issues.append(
                    ValidationIssue(
                        severity="error",
                        code="DUPLICATE_TIMESTAMP",
                        message=f"Duplicate timestamp {bar.timestamp}.",
                        timestamp=bar.timestamp,
                    )
                )
            seen_timestamps.add(bar.timestamp)

            # Out-of-order timestamps.
            if prev_timestamp is not None and bar.timestamp < prev_timestamp:
                bar_issues.append(
                    ValidationIssue(
                        severity="error",
                        code="OUT_OF_ORDER",
                        message=(
                            f"Timestamp {bar.timestamp} is out of order "
                            f"(previous: {prev_timestamp})."
                        ),
                        timestamp=bar.timestamp,
                    )
                )
            prev_timestamp = bar.timestamp

            # Negative volume/spread.
            if bar.tick_volume is not None and bar.tick_volume < 0:
                bar_issues.append(
                    ValidationIssue(
                        severity="error",
                        code="NEGATIVE_VOLUME",
                        message=f"tick_volume {bar.tick_volume} is negative.",
                        timestamp=bar.timestamp,
                    )
                )
            if bar.real_volume is not None and bar.real_volume < 0:
                bar_issues.append(
                    ValidationIssue(
                        severity="error",
                        code="NEGATIVE_VOLUME",
                        message=f"real_volume {bar.real_volume} is negative.",
                        timestamp=bar.timestamp,
                    )
                )
            if bar.spread is not None and bar.spread < 0:
                bar_issues.append(
                    ValidationIssue(
                        severity="error",
                        code="NEGATIVE_SPREAD",
                        message=f"spread {bar.spread} is negative.",
                        timestamp=bar.timestamp,
                    )
                )

            # Incomplete candle flag.
            if bar.is_complete is False:
                bar_issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="INCOMPLETE_CANDLE",
                        message=f"Candle at {bar.timestamp} is incomplete.",
                        timestamp=bar.timestamp,
                    )
                )

            if bar_issues:
                issues.extend(bar_issues)
            else:
                valid_count += 1

        # Missing intervals / gaps (session-aware).
        if total > 1:
            sorted_bars = sorted(bars, key=lambda b: b.timestamp)
            missing: List[datetime] = []
            for i in range(1, len(sorted_bars)):
                prev = sorted_bars[i - 1].timestamp
                curr = sorted_bars[i].timestamp
                expected = prev + expected_step
                while expected < curr:
                    missing.append(expected)
                    expected += expected_step
            if missing:
                session_id = self._session_for_symbol(symbol)
                real_missing = self._filter_expected_closures(
                    session_id, missing, timeframe
                )
                if real_missing:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="MISSING_INTERVALS",
                            message=(
                                f"{len(real_missing)} expected candle(s) missing "
                                f"between {sorted_bars[0].timestamp} and "
                                f"{sorted_bars[-1].timestamp}."
                            ),
                        )
                    )

        return DataQualityReport(
            symbol=symbol,
            timeframe=timeframe,
            total_candles=total,
            valid_candles=valid_count,
            invalid_candles=total - valid_count,
            issues=issues,
            missing_intervals=[],
            session_aware=True,
        )

    def validate_provider_candles(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        bars: List[OHLCBar],
    ) -> DataQualityReport:
        """Alias for validate_bars with additional gap detection context."""
        return self.validate_bars(symbol, timeframe, bars)
