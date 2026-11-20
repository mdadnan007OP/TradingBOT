"""MT5 Connection Diagnostics (read-only, safe).

Reports Python version, MT5 package availability/version, terminal connection
status, terminal version, account mode (DEMO or rejected LIVE), server name
(where safe), discovered instrument count, available symbols, selected symbol
metadata, current quote, and historical candle retrieval status.

Never prints passwords, login numbers, balances, or personal account data.

Fails safely when the MT5 terminal is unavailable or the package is missing.

Usage (from project root):

    python -m src.diagnostics.mt5_diagnostics
    python -m src.diagnostics.mt5_diagnostics --terminal "C:\\MT5\\terminal64.exe"
    python -m src.diagnostics.mt5_diagnostics --symbol XAUUSD
    python -m src.diagnostics.mt5_diagnostics --json

Exit codes:
    0 = diagnostics completed (connection may still be unavailable)
    1 = unexpected failure
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional


def _safe_section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def run_diagnostics(
    terminal_path: Optional[str] = None,
    symbol: str = "XAUUSD",
    as_json: bool = False,
) -> int:
    """Run MT5 diagnostics and print a report.

    Args:
        terminal_path: Optional explicit MT5 terminal executable path.
        symbol: Canonical symbol to probe (quote + candles).
        as_json: Emit a JSON document instead of text.

    Returns:
        Exit code (0 success, 1 failure).
    """
    report: dict = {}

    _safe_section("ENVIRONMENT")
    python_version = platform.python_version()
    arch = platform.machine()
    print(f"Python version : {python_version}")
    print(f"Architecture   : {arch}")
    print(f"Platform       : {platform.platform()}")
    report["python_version"] = python_version
    report["architecture"] = arch
    report["platform"] = platform.platform()

    _safe_section("MT5 PACKAGE")
    try:
        import MetaTrader5 as mt5  # noqa: F401
        mt5_version = getattr(mt5, "__version__", "unknown")
        print(f"MetaTrader5    : installed (version {mt5_version})")
        report["mt5_package"] = "installed"
        report["mt5_package_version"] = mt5_version
    except ImportError:
        print("MetaTrader5    : NOT INSTALLED")
        print("Install with   : pip install MetaTrader5")
        print()
        print("Diagnostics cannot continue without the MetaTrader5 package.")
        if as_json:
            report["status"] = "mt5_not_installed"
            print(json.dumps(report, indent=2))
        return 0

    # From here on, import the adapter lazily so a missing package never
    # breaks module import.
    from src.broker.mt5.mt5_adapter import MT5BrokerAdapter
    from src.broker.mt5.exceptions import (
        MT5LiveAccountError,
        MT5NotInstalledError,
        MT5TerminalNotFoundError,
        MT5TerminalNotRunningError,
    )

    _safe_section("TERMINAL CONNECTION")
    adapter = MT5BrokerAdapter(
        terminal_path=terminal_path,
        canonical_symbols=[symbol],
    )

    try:
        connected = adapter.connect()
    except MT5LiveAccountError as exc:
        # Demo-only safety lock triggered.
        print(f"REJECTED: {exc}")
        print()
        print("The connected account is NOT a demo account. Read-only demo")
        print("policy forbids continuing. Open your MT5 terminal and log in")
        print("to your PU Prime DEMO account, then re-run diagnostics.")
        report["status"] = "live_account_rejected"
        if as_json:
            print(json.dumps(report, indent=2))
        return 0
    except MT5TerminalNotFoundError as exc:
        print(f"TERMINAL NOT FOUND: {exc}")
        print()
        print("Open MetaTrader 5 desktop, log into your PU Prime demo, and")
        print("either leave the terminal running for auto-discovery or pass")
        print("--terminal with the full path to terminal64.exe.")
        report["status"] = "terminal_not_found"
        if as_json:
            print(json.dumps(report, indent=2))
        return 0
    except MT5TerminalNotRunningError as exc:
        print(f"TERMINAL NOT RUNNING: {exc}")
        print()
        print("The MT5 adapter does not auto-launch terminals. Open MetaTrader 5,")
        print("log into your PU Prime DEMO account, keep it running, then retry.")
        report["status"] = "terminal_not_running"
        if as_json:
            print(json.dumps(report, indent=2))
        return 0
    except MT5NotInstalledError as exc:
        print(f"MT5 PACKAGE ERROR: {exc}")
        report["status"] = "mt5_not_installed"
        if as_json:
            print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"CONNECTION FAILED: {exc}")
        report["status"] = "connection_failed"
        if as_json:
            print(json.dumps(report, indent=2))
        return 0

    if not connected:
        print("CONNECTION FAILED: adapter.connect() returned False.")
        report["status"] = "connection_failed"
        if as_json:
            print(json.dumps(report, indent=2))
        return 0

    print("Connection     : CONNECTED")
    report["status"] = "connected"

    _safe_section("ACCOUNT (SAFE SUMMARY)")
    account = adapter.get_account_info()
    if account is not None:
        # Only safe, non-sensitive fields are shown.
        print(f"Account mode   : {account.trade_mode.upper()}")
        print(f"Server         : {account.server}")
        print(f"Currency       : {account.currency}")
        print(f"Trading allowed: {account.trade_allowed}")
        report["account_mode"] = account.trade_mode
        report["server"] = account.server
        report["currency"] = account.currency
        report["trade_allowed"] = account.trade_allowed
    else:
        print("Account info   : unavailable")
        report["account_mode"] = "unknown"

    _safe_section("SYMBOL DISCOVERY")
    diag = adapter.run_diagnostics()
    discovered = diag.get("discovered_symbols", 0)
    mapped = diag.get("mapped_symbols", 0)
    print(f"Discovered instruments : {discovered}")
    print(f"Mapped canonical set   : {mapped}")
    print(f"Terminal version       : {diag.get('terminal_version', 'unknown')}")
    print(f"Terminal build         : {diag.get('terminal_build', 0)}")
    report["discovered_instruments"] = discovered
    report["mapped_symbols"] = mapped
    report["terminal_version"] = diag.get("terminal_version", "unknown")
    report["terminal_build"] = diag.get("terminal_build", 0)

    print()
    print("Symbol discovery report:")
    print(adapter.get_discovery_report())

    _safe_section(f"SELECTED SYMBOL: {symbol}")
    market_data = adapter.get_market_data()
    if market_data is None:
        print("Market data interface unavailable.")
        report["symbol_status"] = "unavailable"
    else:
        # Quote
        quote = market_data.get_quote(symbol)
        if quote is not None:
            print(f"Bid            : {quote.bid}")
            print(f"Ask            : {quote.ask}")
            print(f"Spread         : {quote.spread}")
            print(f"Last           : {quote.last if quote.last is not None else 'n/a'}")
            print(f"Quote time     : {quote.timestamp.isoformat()}")
            report["quote"] = {
                "bid": str(quote.bid),
                "ask": str(quote.ask),
                "spread": str(quote.spread),
                "timestamp": quote.timestamp.isoformat(),
            }
        else:
            print("Quote          : unavailable (symbol may be unknown or market closed)")
            report["quote"] = None

        # Historical candles (completed only)
        from src.market_data.models import MarketTimeframe

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=1)
        try:
            bars = market_data.get_candles(
                symbol,
                MarketTimeframe.H1,
                start_time,
                end_time,
                completed_only=True,
            )
            print(f"Completed H1 candles (last 24h): {len(bars)}")
            if bars:
                newest = bars[-1]
                print(f"Newest candle  : {newest.timestamp.isoformat()} "
                      f"O={newest.open} H={newest.high} L={newest.low} C={newest.close}")
            report["candle_status"] = "ok"
            report["candle_count"] = len(bars)
        except Exception as exc:  # noqa: BLE001
            print(f"Candle retrieval failed: {exc}")
            report["candle_status"] = "failed"

    _safe_section("SAFETY STATUS")
    print("Order placement : DISABLED (read-only demo lock)")
    print("Order closing   : DISABLED (read-only demo lock)")
    print("Positions/orders: not accessible (read-only mode)")
    report["order_placement"] = "disabled"
    report["order_closing"] = "disabled"

    # Disconnect gracefully.
    adapter.disconnect()

    if as_json:
        print()
        print(json.dumps(report, indent=2))

    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="MT5 connection diagnostics (read-only, demo-only)."
    )
    parser.add_argument(
        "--terminal",
        default=None,
        help="Explicit path to the MT5 terminal64.exe executable.",
    )
    parser.add_argument(
        "--symbol",
        default="XAUUSD",
        help="Canonical symbol to probe (default: XAUUSD).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report.",
    )
    args = parser.parse_args(argv)
    return run_diagnostics(
        terminal_path=args.terminal,
        symbol=args.symbol,
        as_json=args.json,
    )


if __name__ == "__main__":
    sys.exit(main())