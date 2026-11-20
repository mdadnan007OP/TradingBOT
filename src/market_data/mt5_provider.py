"""MT5 Market Data Provider implementing MarketDataProvider interface."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from src.market_data.base import MarketDataProvider
from src.market_data.models import (
    MarketSymbol,
    MarketTimeframe,
    OHLCBar,
    MarketQuote,
    DataSource,
    InstrumentType,
)
from src.broker.mt5 import MT5BrokerAdapter
from src.broker.mt5.exceptions import MT5Error

logger = logging.getLogger(__name__)


class MT5MarketDataProvider(MarketDataProvider):
    """MT5 implementation of MarketDataProvider.

    Integrates MT5 broker adapter with the Phase 2 Market Data Engine.
    """

    def __init__(
        self,
        mt5_adapter: MT5BrokerAdapter,
        name: str = "MT5 (PU Prime Demo)",
    ) -> None:
        """Initialize MT5 market data provider.

        Args:
            mt5_adapter: Connected MT5BrokerAdapter instance.
            name: Human-readable provider name.
        """
        self._adapter = mt5_adapter
        self._name = name
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_connected(self) -> bool:
        return self._adapter.is_connected

    @property
    def is_simulated(self) -> bool:
        return False  # MT5 provides live broker data

    def connect(self) -> bool:
        """Connect to MT5 via the adapter."""
        if self._adapter.is_connected:
            return True
        return self._adapter.connect()

    def disconnect(self) -> bool:
        """Disconnect from MT5 via the adapter."""
        return self._adapter.disconnect()

    def get_symbols(self) -> List[MarketSymbol]:
        """Get supported symbols from MT5."""
        if not self.is_connected:
            return []

        instruments = self._adapter.get_instruments()
        symbols = []
        for inst in instruments:
            symbols.append(MarketSymbol(
                symbol=inst.symbol,
                name=inst.name,
                instrument_type=inst.instrument_type,
                base_currency=inst.base_currency,
                quote_currency=inst.quote_currency,
            ))
        return symbols

    def get_timeframes(self) -> List[MarketTimeframe]:
        """Get supported timeframes."""
        # MT5 supports all standard timeframes
        return list(MarketTimeframe)

    def get_candles(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
    ) -> List[OHLCBar]:
        """Get historical OHLC bars from MT5."""
        if not self.is_connected or self._adapter.get_market_data() is None:
            return []

        market_data = self._adapter.get_market_data()
        try:
            return market_data.get_candles(
                canonical_symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                completed_only=True,  # Only completed candles for historical data
            )
        except Exception as exc:
            self._logger.exception("Error getting candles from MT5: %s", exc)
            return []

    def get_latest_candle(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
    ) -> Optional[OHLCBar]:
        """Get the most recent candle from MT5."""
        if not self.is_connected or self._adapter.get_market_data() is None:
            return None

        market_data = self._adapter.get_market_data()
        try:
            return market_data.get_latest_candle(
                canonical_symbol=symbol,
                timeframe=timeframe,
                completed_only=True,  # Last completed candle
            )
        except Exception as exc:
            self._logger.exception("Error getting latest candle from MT5: %s", exc)
            return None

    def get_quote(self, symbol: str) -> Optional[MarketQuote]:
        """Get current bid/ask quote from MT5."""
        if not self.is_connected or self._adapter.get_market_data() is None:
            return None

        market_data = self._adapter.get_market_data()
        try:
            return market_data.get_quote(symbol)
        except Exception as exc:
            self._logger.exception("Error getting quote from MT5: %s", exc)
            return None