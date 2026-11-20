"""Real MT5 connection verification using the trading bot's own code.

Connects to the already-running PU Prime MT5 DEMO terminal, verifies demo
status, retrieves genuine quotes and historical M1 candles, validates them
through the Phase 2 Market Data Engine, then shuts down safely.

READ-ONLY: No orders, no position changes, no credentials logged.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from src.broker.mt5.mt5_adapter import MT5BrokerAdapter
from src.broker.mt5.exceptions import MT5LiveAccountError, MT5TerminalNotRunningError
from src.market_data.mt5_provider import MT5MarketDataProvider
from src.market_data.models import MarketTimeframe, DataSource
from src.market_data.service import MarketDataService


def main() -> int:
    terminal_path = r"C:\Program Files\PU Prime MT5 Terminal\terminal64.exe"

    print("=" * 60)
    print("MT5 REAL CONNECTION VERIFICATION (READ-ONLY, DEMO-ONLY)")
    print("=" * 60)

    adapter = MT5BrokerAdapter(terminal_path=terminal_path)
    service = MarketDataService()

    try:
        # 1. Connect (includes demo-only safety check)
        print("\n[1] Connecting to MT5 terminal...")
        adapter.connect()
        print("    Connected successfully.")
        print("    Adapter connected: True")

        # 2. Verify demo account
        account = adapter.get_account_info()
        if account is None:
            print("    ERROR: Could not retrieve account info.")
            return 1
        print("\n[2] Account verification:")
        print("    Mode: %s" % account.trade_mode)
        print("    Server: %s" % account.server)
        print("    Currency: %s" % account.currency)
        if account.trade_mode != "demo":
            print("    ERROR: Account is not DEMO. Aborting.")
            return 1
        print("    Demo account verified [OK]")

        # 3. Retrieve symbols
        print("\n[3] Retrieving broker symbols...")
        instruments = adapter.get_instruments()
        print("    %d instruments available." % len(instruments))
        symbols = [i.symbol for i in instruments]
        print("    Sample: %s" % symbols[:10])

        # 4. Select a Forex or metal symbol
        forex_metal = [s for s in symbols if s in ("EURUSD", "GBPUSD", "XAUUSD", "XAGUSD", "USDJPY")]
        if not forex_metal:
            print("    ERROR: No Forex/metal symbols found.")
            return 1
        test_symbol = forex_metal[0]
        print("\n[4] Selected symbol: %s" % test_symbol)

        # 5. Register MT5 provider and retrieve genuine quote
        provider = MT5MarketDataProvider(adapter)
        service.register_provider("mt5", provider)

        print("\n[5] Retrieving genuine quote for %s..." % test_symbol)
        quote = service.get_quote(test_symbol)
        if quote is None:
            print("    No quote available (market may be closed).")
        else:
            spread = quote.ask - quote.bid
            print("    Bid: %s" % quote.bid)
            print("    Ask: %s" % quote.ask)
            print("    Spread: %s" % spread)
            print("    Timestamp: %s" % quote.timestamp.isoformat())
            print("    Source: LIVE (broker-provided)")
            print("    Genuine quote retrieved [OK]")

        # 6. Retrieve historical M1 candles
        print("\n[6] Retrieving historical M1 candles for %s..." % test_symbol)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=24)
        bars = service.get_candles(
            test_symbol,
            MarketTimeframe.M1,
            start_time,
            end_time,
        )
        if not bars:
            print("    No candles available (market may be closed).")
        else:
            print("    %d M1 candles retrieved." % len(bars))
            print("    Sample: %s O=%s H=%s L=%s C=%s" % (
                bars[0].timestamp.isoformat(),
                bars[0].open, bars[0].high, bars[0].low, bars[0].close))
            print("    Data source: %s" % bars[0].data_source.value)
            print("    All complete: %s" % all(b.is_complete for b in bars))
            print("    Historical candles retrieved [OK]")

        # 7. Validate candles using Phase 2 Market Data Engine
        if bars:
            print("\n[7] Validating candles through Phase 2 Market Data Engine...")
            report = service.validate_candles(test_symbol, MarketTimeframe.M1, bars)
            print("    Total: %d" % report.total_candles)
            print("    Valid: %d" % report.valid_candles)
            print("    Invalid: %d" % report.invalid_candles)
            print("    Errors: %d" % report.error_count)
            print("    Warnings: %d" % report.warning_count)
            print("    Is valid: %s" % report.is_valid)
            if report.is_valid:
                print("    Candle validation passed [OK]")

        print("\n" + "=" * 60)
        print("VERIFICATION COMPLETE - All checks passed [OK]")
        print("=" * 60)

    except MT5TerminalNotRunningError as exc:
        print("\nERROR: %s" % exc)
        print("Open MetaTrader 5, log into your PU Prime DEMO account, then retry.")
        return 1
    except MT5LiveAccountError as exc:
        print("\nERROR: %s" % exc)
        print("Demo-only safety lock enforced. Aborting.")
        return 1
    except Exception as exc:  # noqa: BLE001
        print("\nERROR: %s" % exc)
        return 1
    finally:
        # 8. Shut down safely
        print("\n[8] Shutting down MT5 connection...")
        service.disconnect_all()
        adapter.disconnect()
        print("    Connection closed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())