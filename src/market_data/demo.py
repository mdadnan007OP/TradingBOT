"""Market Data Engine demonstration script.

Shows:
    1. Mock market data provider - simulated OHLC candle generation.
    2. CSV historical data provider - loading from local CSV files.
    3. Data validation - quality reports.
    4. Data processing - sorting, filtering, gap detection.

Run from the project root:

    python -m src.market_data.demo
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.market_data.csv_provider import HistoricalCSVProvider
from src.market_data.mock_provider import MockMarketDataProvider
from src.market_data.models import MarketTimeframe, OHLCBar
from src.market_data.processor import DataProcessor
from src.market_data.service import MarketDataService
from src.market_data.validator import DataValidator


def _utc(y: int, m: int, d: int, H: int = 0, M: int = 0) -> datetime:
    return datetime(y, m, d, H, M, tzinfo=timezone.utc)


def demo_mock_provider():
    """Demonstrate simulated OHLC candle generation."""
    print("=" * 60)
    print("DEMO 1: Mock Market Data Provider (Simulated OHLC Bars)")
    print("=" * 60)

    provider = MockMarketDataProvider(seed=42)
    provider.connect()

    print(f"Provider: {provider.name}")
    print(f"Simulated: {provider.is_simulated}")
    print(f"Connected: {provider.is_connected}")
    print()

    symbols = [s.symbol for s in provider.get_symbols()]
    print(f"Supported symbols: {symbols}")
    print(f"Supported timeframes: {[t.value for t in provider.get_timeframes()]}")
    print()

    start = _utc(2024, 1, 1, 0, 0)
    end = _utc(2024, 1, 1, 0, 30)  # 30 minutes of M1 bars
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, start, end)

    print(f"Generated {len(bars)} M1 bars for EURUSD:")
    for bar in bars[:5]:
        print(
            f"  {bar.timestamp} | O={bar.open} H={bar.high} "
            f"L={bar.low} C={bar.close} | tick_vol={bar.tick_volume} "
            f"real_vol={bar.real_volume} spread={bar.spread}"
        )
    if len(bars) > 5:
        print(f"  ... ({len(bars) - 5} more bars)")

    # Reproducibility check.
    provider2 = MockMarketDataProvider(seed=42)
    provider2.connect()
    bars2 = provider2.get_candles("EURUSD", MarketTimeframe.M1, start, end)
    provider2.disconnect()
    assert [b.open for b in bars] == [b.open for b in bars2]
    print("\nReproducibility: same seed produces identical output.")

    # Quote.
    quote = provider.get_quote("EURUSD")
    print(f"\nLatest quote: bid={quote.bid} ask={quote.ask} spread={quote.spread}")

    provider.disconnect()
    print()


def demo_csv_provider():
    """Demonstrate loading historical candles from CSV files."""
    print("=" * 60)
    print("DEMO 2: Historical CSV Provider")
    print("=" * 60)

    csv_dir = "data/historical"
    os.makedirs(csv_dir, exist_ok=True)

    # Write a sample CSV file.
    csv_path = os.path.join(csv_dir, "XAUUSD_H1.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["timestamp", "open", "high", "low", "close", "tick_volume", "real_volume", "spread"]
        )
        base = Decimal("2000.00")
        for i in range(24):
            ts = _utc(2024, 1, 1, i, 0)
            open_p = base + Decimal(str(i * 0.5))
            high_p = open_p + Decimal("5.00")
            low_p = open_p - Decimal("5.00")
            close_p = open_p + Decimal("2.00")
            writer.writerow(
                [ts.strftime("%Y-%m-%d %H:%M:%S"),
                 str(open_p), str(high_p), str(low_p), str(close_p),
                 "500", "5000", "0.03"]
            )

    provider = HistoricalCSVProvider(data_dir=csv_dir, symbol="XAUUSD", timeframe=MarketTimeframe.H1)
    provider.connect()

    print(f"Provider: {provider.name}")
    print(f"Simulated: {provider.is_simulated}")
    print(f"Data directory: {csv_dir}")
    print()

    start = _utc(2024, 1, 1, 0, 0)
    end = _utc(2024, 1, 1, 23, 0)
    bars = provider.get_candles("XAUUSD", MarketTimeframe.H1, start, end)

    print(f"Loaded {len(bars)} H1 bars for XAUUSD:")
    for bar in bars[:5]:
        print(
            f"  {bar.timestamp} | O={bar.open} H={bar.high} "
            f"L={bar.low} C={bar.close} | tick_vol={bar.tick_volume} "
            f"real_vol={bar.real_volume} spread={bar.spread}"
        )

    # Latest candle.
    latest = provider.get_latest_candle("XAUUSD", MarketTimeframe.H1)
    print(f"\nLatest candle: {latest.timestamp} C={latest.close}")

    provider.disconnect()
    print()


def demo_validation():
    """Demonstrate data validation and quality reporting."""
    print("=" * 60)
    print("DEMO 3: Data Validation Engine")
    print("=" * 60)

    validator = DataValidator()

    # Valid bars.
    valid_bars = [
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=datetime(2024, 1, 1, 0, i, tzinfo=timezone.utc),
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
        )
        for i in range(5)
    ]

    # Invalid bars (duplicate timestamp, bad OHLC).
    invalid_bars = valid_bars + [
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),  # duplicate
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
        ),
    ]

    report = validator.validate_bars("EURUSD", MarketTimeframe.M1, invalid_bars)
    print(f"Total candles: {report.total_candles}")
    print(f"Valid: {report.valid_candles}")
    print(f"Invalid: {report.invalid_candles}")
    print(f"Is valid: {report.is_valid}")
    print(f"Errors: {report.error_count}")
    print(f"Warnings: {report.warning_count}")
    for issue in report.issues:
        print(f"  [{issue.severity}] {issue.code}: {issue.message}")
    print()


def demo_processing():
    """Demonstrate data processing operations."""
    print("=" * 60)
    print("DEMO 4: Data Processing Engine")
    print("=" * 60)

    bars = [
        OHLCBar(
            symbol="GBPUSD",
            timeframe=MarketTimeframe.M5,
            timestamp=datetime(2024, 1, 1, 0, 10, tzinfo=timezone.utc),
            open=Decimal("1.2700"),
            high=Decimal("1.2710"),
            low=Decimal("1.2690"),
            close=Decimal("1.2705"),
        ),
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
        ),
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),  # duplicate
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
        ),
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.H1,
            timestamp=datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc),
            open=Decimal("1.1005"),
            high=Decimal("1.1020"),
            low=Decimal("1.1000"),
            close=Decimal("1.1015"),
        ),
    ]

    print(f"Original bars: {len(bars)}")

    # Standardize (sort + deduplicate).
    standardized = DataProcessor.standardize(bars)
    print(f"After standardization: {len(standardized)}")

    # Filter by symbol.
    eurusd = DataProcessor.filter_by_symbol(standardized, "EURUSD")
    print(f"EURUSD bars: {len(eurusd)}")

    # Filter by timeframe.
    m1 = DataProcessor.filter_by_timeframe(standardized, MarketTimeframe.M1)
    print(f"M1 bars: {len(m1)}")

    # Date range filter.
    ranged = DataProcessor.filter_by_date_range(
        standardized,
        datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 1, 0, 30, tzinfo=timezone.utc),
    )
    print(f"Bars in [00:00, 00:30]: {len(ranged)}")

    # Missing intervals.
    missing = DataProcessor.detect_missing_intervals([
        OHLCBar(symbol="EURUSD", timeframe=MarketTimeframe.M1,
                timestamp=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
                open=Decimal("1.1"), high=Decimal("1.101"), low=Decimal("1.099"), close=Decimal("1.1005")),
        OHLCBar(symbol="EURUSD", timeframe=MarketTimeframe.M1,
                timestamp=datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc),
                open=Decimal("1.1"), high=Decimal("1.101"), low=Decimal("1.099"), close=Decimal("1.1005")),
    ])
    print(f"Missing M1 intervals: {len(missing)}")
    print()


def demo_service():
    """Demonstrate the MarketDataService layer."""
    print("=" * 60)
    print("DEMO 5: Market Data Service Layer")
    print("=" * 60)

    service = MarketDataService()
    provider = MockMarketDataProvider(seed=99)
    service.register_provider("mock_sim", provider)

    print(f"Registered providers: {service.list_providers()}")
    print(f"Active provider: {service.get_active_provider().name}")

    bars = service.get_candles("AUDUSD", MarketTimeframe.H4, _utc(2024, 1, 1), _utc(2024, 1, 2))
    print(f"Retrieved {len(bars)} H4 bars for AUDUSD")

    report = service.validate_candles("AUDUSD", MarketTimeframe.H4, bars)
    print(f"Validation: {report.valid_candles}/{report.total_candles} valid")

    service.disconnect_all()
    print()


if __name__ == "__main__":
    demo_mock_provider()
    demo_csv_provider()
    demo_validation()
    demo_processing()
    demo_service()
    print("All demonstrations completed successfully.")
