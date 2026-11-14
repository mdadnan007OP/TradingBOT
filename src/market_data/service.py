"""Service layer for the Market Data Engine.

Orchestrates providers, validator, and processor into a unified interface
usable by downstream engines (indicators, strategies, backtesting).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.market_data.base import MarketDataProvider
from src.market_data.models import (
    DataQualityReport,
    DEFAULT_INSTRUMENT_SPECS,
    DEFAULT_SYMBOLS,
    InstrumentSpec,
    MarketQuote,
    MarketSymbol,
    MarketTimeframe,
    OHLCBar,
)
from src.market_data.processor import DataProcessor
from src.market_data.sessions import DEFAULT_SESSIONS, SessionCalendar
from src.market_data.validator import DataValidator

logger = logging.getLogger(__name__)


class MarketDataService:
    """Unified service for retrieving and validating market data.

    Responsibilities:
        * Register and switch between data providers (mock, CSV, future MT5).
        * Manage instrument specifications (universal registry).
        * Manage market session calendars.
        * Retrieve candles with session-aware validation.
        * Process bars (sort, filter, deduplicate).
        * Expose data quality reports.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, MarketDataProvider] = {}
        self._active_provider: Optional[str] = None
        self._instrument_specs: Dict[str, InstrumentSpec] = {
            s.canonical_symbol: s for s in DEFAULT_INSTRUMENT_SPECS
        }
        self._session_calendar = SessionCalendar(dict(DEFAULT_SESSIONS))
        self._validator = DataValidator(
            instrument_specs=self._instrument_specs,
            session_calendar=self._session_calendar,
        )
        self._processor = DataProcessor()
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def register_provider(self, name: str, provider: MarketDataProvider) -> bool:
        """Register a data provider under ``name``."""
        try:
            provider.connect()
            self._providers[name] = provider
            if self._active_provider is None:
                self._active_provider = name
            self._logger.info(
                "Registered market data provider: %s (%s)", name, provider.name
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Failed to register provider %s: %s", name, exc)
            return False

    def set_provider(self, name: str) -> bool:
        """Switch the active provider by name."""
        if name not in self._providers:
            self._logger.warning("Provider %s not registered", name)
            return False
        self._active_provider = name
        return True

    def get_active_provider(self) -> Optional[MarketDataProvider]:
        """Return the currently active provider, or None."""
        if self._active_provider is None:
            return None
        return self._providers[self._active_provider]

    def list_providers(self) -> List[str]:
        """Return registered provider names."""
        return list(self._providers.keys())

    # ------------------------------------------------------------------
    # Instrument registry
    # ------------------------------------------------------------------

    def register_instrument_spec(self, spec: InstrumentSpec) -> None:
        """Register or update an instrument specification.

        Example::

            service.register_instrument_spec(
                InstrumentSpec(
                    canonical_symbol="WTIUSD",
                    broker_symbol="WTI",
                    name="WTI Crude Oil",
                    instrument_type=InstrumentType.ENERGY,
                    price_precision=3,
                    tick_size=Decimal("0.001"),
                    contract_size=Decimal("1000"),
                    market_session="energy",
                )
            )
        """
        self._instrument_specs[spec.canonical_symbol] = spec
        self._validator.instrument_specs[spec.canonical_symbol] = spec
        self._logger.info(
            "Registered instrument spec: %s (%s)", spec.canonical_symbol, spec.name
        )

    def get_instrument_spec(self, canonical_symbol: str) -> Optional[InstrumentSpec]:
        """Return the InstrumentSpec for a symbol, or None."""
        return self._instrument_specs.get(canonical_symbol)

    def list_instrument_specs(self) -> List[InstrumentSpec]:
        """Return all registered instrument specifications."""
        return list(self._instrument_specs.values())

    def get_symbols(self) -> List[MarketSymbol]:
        provider = self.get_active_provider()
        if provider is None:
            return list(DEFAULT_SYMBOLS)
        return provider.get_symbols()

    def get_timeframes(self) -> List[MarketTimeframe]:
        provider = self.get_active_provider()
        if provider is None:
            return list(MarketTimeframe)
        return provider.get_timeframes()

    # ------------------------------------------------------------------
    # Session calendar
    # ------------------------------------------------------------------

    def get_session_calendar(self) -> SessionCalendar:
        """Return the session calendar."""
        return self._session_calendar

    def register_session(self, session_id: str, session) -> None:
        """Register or override a market session definition."""
        self._session_calendar.register_session(session_id, session)

    # ------------------------------------------------------------------
    # Candle retrieval
    # ------------------------------------------------------------------

    def get_candles(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
        validate: bool = True,
    ) -> List[OHLCBar]:
        """Retrieve candles from the active provider, optionally validated."""
        provider = self.get_active_provider()
        if provider is None:
            self._logger.warning("No active market data provider")
            return []

        bars = provider.get_candles(symbol, timeframe, start_time, end_time)
        bars = DataProcessor.standardize(bars)

        if validate:
            report = self._validator.validate_bars(symbol, timeframe, bars)
            if not report.is_valid:
                self._logger.warning(
                    "Validation issues for %s %s: %d errors, %d warnings",
                    symbol,
                    timeframe.value,
                    report.error_count,
                    report.warning_count,
                )

        return bars

    def get_latest_candle(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
    ) -> Optional[OHLCBar]:
        provider = self.get_active_provider()
        if provider is None:
            return None
        return provider.get_latest_candle(symbol, timeframe)

    def get_quote(self, symbol: str) -> Optional[MarketQuote]:
        provider = self.get_active_provider()
        if provider is None:
            return None
        return provider.get_quote(symbol)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_candles(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        bars: List[OHLCBar],
    ) -> DataQualityReport:
        """Validate a list of bars and return a quality report."""
        return self._validator.validate_bars(symbol, timeframe, bars)

    def get_missing_intervals(
        self,
        bars: List[OHLCBar],
    ) -> List[datetime]:
        """Detect missing candle intervals in a bar list."""
        return DataProcessor.detect_missing_intervals(bars)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter_symbol(self, bars: List[OHLCBar], symbol: str) -> List[OHLCBar]:
        return DataProcessor.filter_by_symbol(bars, symbol)

    def filter_timeframe(
        self, bars: List[OHLCBar], timeframe: MarketTimeframe
    ) -> List[OHLCBar]:
        return DataProcessor.filter_by_timeframe(bars, timeframe)

    def filter_date_range(
        self,
        bars: List[OHLCBar],
        start_time: datetime,
        end_time: datetime,
    ) -> List[OHLCBar]:
        return DataProcessor.filter_by_date_range(bars, start_time, end_time)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def disconnect_all(self) -> None:
        for name, provider in self._providers.items():
            try:
                provider.disconnect()
                self._logger.info("Disconnected provider: %s", name)
            except Exception as exc:  # noqa: BLE001
                self._logger.exception("Error disconnecting %s: %s", name, exc)
        self._providers.clear()
        self._active_provider = None
