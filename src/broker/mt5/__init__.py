"""MT5 Broker Adapter Package."""

from __future__ import annotations

from src.broker.mt5.mt5_adapter import MT5BrokerAdapter
from src.broker.mt5.connection import MT5ConnectionManager, MT5TerminalInfo, MT5AccountInfo
from src.broker.mt5.symbol_discovery import MT5SymbolDiscovery, MT5SymbolInfo, SymbolMapping
from src.broker.mt5.market_data import MT5MarketData
from src.broker.mt5.exceptions import (
    MT5Error,
    MT5InitializationError,
    MT5ConnectionError,
    MT5NotInstalledError,
    MT5TerminalNotFoundError,
    MT5AccountError,
    MT5LiveAccountError,
    MT5SymbolError,
    MT5DataError,
)

__all__ = [
    "MT5BrokerAdapter",
    "MT5ConnectionManager",
    "MT5TerminalInfo",
    "MT5AccountInfo",
    "MT5SymbolDiscovery",
    "MT5SymbolInfo",
    "SymbolMapping",
    "MT5MarketData",
    "MT5Error",
    "MT5InitializationError",
    "MT5ConnectionError",
    "MT5NotInstalledError",
    "MT5TerminalNotFoundError",
    "MT5AccountError",
    "MT5LiveAccountError",
    "MT5SymbolError",
    "MT5DataError",
]