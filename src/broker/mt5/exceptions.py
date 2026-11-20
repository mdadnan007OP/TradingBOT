"""MT5-specific exceptions."""

from __future__ import annotations


class MT5Error(Exception):
    """Base exception for MT5 adapter errors."""
    pass


class MT5InitializationError(MT5Error):
    """Raised when MT5 terminal initialization fails."""
    pass


class MT5ConnectionError(MT5Error):
    """Raised when connection to MT5 terminal fails."""
    pass


class MT5NotInstalledError(MT5Error):
    """Raised when MetaTrader5 Python package is not installed."""
    pass


class MT5TerminalNotFoundError(MT5Error):
    """Raised when MT5 terminal executable cannot be located."""
    pass


class MT5TerminalNotRunningError(MT5Error):
    """Raised when no MT5 terminal process is running.

    The adapter does not auto-launch terminals; the user must open MetaTrader 5
    and log into their PU Prime DEMO account before connecting.
    """
    pass


class MT5AccountError(MT5Error):
    """Raised when account validation fails."""
    pass


class MT5LiveAccountError(MT5Error):
    """Raised when a live account is detected (demo-only policy)."""
    pass


class MT5SymbolError(MT5Error):
    """Raised when symbol operations fail."""
    pass


class MT5DataError(MT5Error):
    """Raised when market data retrieval fails."""
    pass