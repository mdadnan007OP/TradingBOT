"""Market Data Engine package.

Provides simulated and historical market data collection, validation, and
processing for the Forex trading bot. All data is broker-agnostic; no MT5 or
real broker connections are used in Phase 2.
"""

from src.market_data.base import MarketDataProvider
from src.market_data.csv_provider import HistoricalCSVProvider
from src.market_data.mock_provider import MockMarketDataProvider
from src.market_data.models import (
    CandleCompletion,
    DataQualityReport,
    DataSource,
    DEFAULT_INSTRUMENT_SPECS,
    DEFAULT_SYMBOLS,
    InstrumentSpec,
    InstrumentType,
    MarketQuote,
    MarketSymbol,
    MarketTimeframe,
    OHLCBar,
    VolumeType,
    spec_for_symbol,
    ValidationIssue,
)
from src.market_data.processor import DataProcessor
from src.market_data.sessions import (
    DEFAULT_SESSIONS,
    MarketSession,
    SessionCalendar,
)
from src.market_data.service import MarketDataService
from src.market_data.validator import DataValidator

__version__ = "0.2.1"

__all__ = [
    "MarketDataProvider",
    "HistoricalCSVProvider",
    "MockMarketDataProvider",
    "MarketDataService",
    "DataValidator",
    "DataProcessor",
    "SessionCalendar",
    "MarketSession",
    "DEFAULT_SESSIONS",
    "MarketSymbol",
    "MarketTimeframe",
    "OHLCBar",
    "MarketQuote",
    "DataQualityReport",
    "ValidationIssue",
    "InstrumentSpec",
    "InstrumentType",
    "DataSource",
    "VolumeType",
    "CandleCompletion",
    "DEFAULT_SYMBOLS",
    "DEFAULT_INSTRUMENT_SPECS",
    "spec_for_symbol",
]
