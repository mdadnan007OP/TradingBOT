"""Provider interface for the Market Data Engine.

Defines the ``MarketDataProvider`` abstract base class that all data providers
(mock, CSV, future MT5) must implement. The processing engine depends only on
this interface, making it provider-agnostic.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from src.market_data.models import (
    DEFAULT_SYMBOLS,
    MarketQuote,
    MarketSymbol,
    MarketTimeframe,
    OHLCBar,
)

logger = logging.getLogger(__name__)


class MarketDataProvider(ABC):
    """Abstract interface every market data provider must implement.

    Responsibilities:
        * Advertise supported symbols and timeframes.
        * Connect/disconnect from the data source (mock/CSV/MT5).
        * Retrieve historical OHLC bars.
        * Retrieve the latest tick/quote.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the provider is currently connected to its data source."""

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        """True if this provider generates simulated (non-real) data."""

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the data source. Return True on success."""

    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from the data source. Return True on success."""

    @abstractmethod
    def get_symbols(self) -> List[MarketSymbol]:
        """Return the list of supported symbols."""

    @abstractmethod
    def get_timeframes(self) -> List[MarketTimeframe]:
        """Return the list of supported timeframes."""

    @abstractmethod
    def get_candles(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
    ) -> List[OHLCBar]:
        """Return historical OHLC bars for ``symbol``/``timeframe`` in range."""

    @abstractmethod
    def get_latest_candle(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
    ) -> Optional[OHLCBar]:
        """Return the most recent candle for ``symbol``/``timeframe``."""

    @abstractmethod
    def get_quote(self, symbol: str) -> Optional[MarketQuote]:
        """Return the latest bid/ask quote for ``symbol``."""
