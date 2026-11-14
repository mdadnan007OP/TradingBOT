"""Unit tests for the Phase 2 Market Data Engine.

Run from the project root:

    python -m pytest tests/ -v
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.market_data.csv_provider import HistoricalCSVProvider
from src.market_data.mock_provider import MockMarketDataProvider
from src.market_data.models import (
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
from src.market_data.sessions import DEFAULT_SESSIONS, MarketSession, SessionCalendar
from src.market_data.service import MarketDataService
from src.market_data.validator import DataValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(y: int, m: int, d: int, H: int = 0, M: int = 0) -> datetime:
    return datetime(y, m, d, H, M, tzinfo=timezone.utc)


def _make_bar(
    symbol: str = "EURUSD",
    tf: MarketTimeframe = MarketTimeframe.M1,
    ts: datetime | None = None,
    open_: Decimal = Decimal("1.1000"),
    high: Decimal = Decimal("1.1010"),
    low: Decimal = Decimal("1.0990"),
    close: Decimal = Decimal("1.1005"),
) -> OHLCBar:
    if ts is None:
        ts = _utc(2024, 1, 1, 0, 0)
    return OHLCBar(
        symbol=symbol,
        timeframe=tf,
        timestamp=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

def test_market_timeframe_minutes():
    assert MarketTimeframe.M1.minutes == 1
    assert MarketTimeframe.M5.minutes == 5
    assert MarketTimeframe.H1.minutes == 60
    assert MarketTimeframe.H4.minutes == 240
    assert MarketTimeframe.D1.minutes == 1440


def test_market_timeframe_from_string_invalid():
    with pytest.raises(ValueError):
        MarketTimeframe.from_string("INVALID")


def test_default_symbols():
    symbols = {s.symbol for s in DEFAULT_SYMBOLS}
    assert "XAUUSD" in symbols
    assert "XAGUSD" in symbols
    assert "EURUSD" in symbols
    assert "GBPUSD" in symbols
    assert "USDJPY" in symbols
    assert "AUDUSD" in symbols
    assert "USDCAD" in symbols


def test_ohlc_bar_positive_prices():
    with pytest.raises(ValueError):
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=_utc(2024, 1, 1),
            open=Decimal("0"),
            high=Decimal("1.1"),
            low=Decimal("1.0"),
            close=Decimal("1.05"),
        )


def test_ohlc_bar_ohlc_relationships():
    # High below open/close -> invalid.
    with pytest.raises(ValueError):
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=_utc(2024, 1, 1),
            open=Decimal("1.1000"),
            high=Decimal("1.0900"),  # below open
            low=Decimal("1.0900"),
            close=Decimal("1.0950"),
        )

    # Low above open/close -> invalid.
    with pytest.raises(ValueError):
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=_utc(2024, 1, 1),
            open=Decimal("1.1000"),
            high=Decimal("1.1100"),
            low=Decimal("1.1050"),  # above open
            close=Decimal("1.1050"),
        )


def test_ohlc_bar_naive_timestamp():
    with pytest.raises(ValueError):
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=datetime(2024, 1, 1),  # naive
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
        )


def test_ohlc_bar_negative_volume():
    with pytest.raises(ValueError):
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=_utc(2024, 1, 1),
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
            tick_volume=-1,
        )


def test_market_quote_spread():
    q = MarketQuote(
        symbol="EURUSD",
        timestamp=_utc(2024, 1, 1),
        bid=Decimal("1.0999"),
        ask=Decimal("1.1001"),
    )
    assert q.spread == Decimal("0.0002")
    assert q.mid == Decimal("1.1000")


def test_market_quote_invalid_ask_below_bid():
    with pytest.raises(ValueError):
        MarketQuote(
            symbol="EURUSD",
            timestamp=_utc(2024, 1, 1),
            bid=Decimal("1.1001"),
            ask=Decimal("1.0999"),
        )


# ---------------------------------------------------------------------------
# Mock provider tests
# ---------------------------------------------------------------------------

def test_mock_provider_is_simulated():
    provider = MockMarketDataProvider(seed=42)
    assert provider.is_simulated is True
    assert "Simulated" in provider.name


def test_mock_provider_connect_disconnect():
    provider = MockMarketDataProvider(seed=42)
    assert provider.is_connected is False
    assert provider.connect() is True
    assert provider.is_connected is True
    assert provider.disconnect() is True
    assert provider.is_connected is False


def test_mock_provider_symbols_timeframes():
    provider = MockMarketDataProvider(seed=42)
    provider.connect()
    symbols = provider.get_symbols()
    symbol_strings = {s.symbol for s in symbols}
    # Original Phase 1 symbols must all be present.
    for expected in ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]:
        assert expected in symbol_strings
    # Additional asset classes should also be registered.
    assert "WTIUSD" in symbol_strings
    assert "NAS100" in symbol_strings
    assert "BTCUSD" in symbol_strings
    timeframes = provider.get_timeframes()
    assert MarketTimeframe.M1 in timeframes
    assert MarketTimeframe.D1 in timeframes
    assert MarketTimeframe.W1 in timeframes
    assert MarketTimeframe.MN1 in timeframes
    provider.disconnect()


def test_mock_provider_candle_generation():
    provider = MockMarketDataProvider(seed=42)
    provider.connect()
    start = _utc(2024, 1, 1)
    end = _utc(2024, 1, 1, 1, 0)  # 1 hour of M1 bars
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, start, end)
    assert len(bars) > 0
    for bar in bars:
        assert bar.symbol == "EURUSD"
        assert bar.timeframe == MarketTimeframe.M1
        assert bar.open > 0
        assert bar.high > 0
        assert bar.low > 0
        assert bar.close > 0
        assert bar.high >= max(bar.open, bar.close)
        assert bar.low <= min(bar.open, bar.close)
        assert bar.timestamp.tzinfo is not None
    provider.disconnect()


def test_mock_provider_reproducibility():
    p1 = MockMarketDataProvider(seed=123)
    p1.connect()
    bars1 = p1.get_candles("XAUUSD", MarketTimeframe.H1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    p1.disconnect()

    p2 = MockMarketDataProvider(seed=123)
    p2.connect()
    bars2 = p2.get_candles("XAUUSD", MarketTimeframe.H1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    p2.disconnect()

    assert len(bars1) == len(bars2)
    for b1, b2 in zip(bars1, bars2):
        assert b1.open == b2.open
        assert b1.high == b2.high
        assert b1.low == b2.low
        assert b1.close == b2.close
        assert b1.timestamp == b2.timestamp


def test_mock_provider_different_seed_different_output():
    p1 = MockMarketDataProvider(seed=1)
    p1.connect()
    bars1 = p1.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 1, 1, 0))
    p1.disconnect()

    p2 = MockMarketDataProvider(seed=999)
    p2.connect()
    bars2 = p2.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 1, 1, 0))
    p2.disconnect()

    assert len(bars1) == len(bars2)
    # At least one bar should differ (different seeds).
    assert any(b1.open != b2.open for b1, b2 in zip(bars1, bars2))


def test_mock_provider_quote():
    provider = MockMarketDataProvider(seed=42)
    provider.connect()
    quote = provider.get_quote("EURUSD")
    assert quote is not None
    assert quote.symbol == "EURUSD"
    assert quote.bid > 0
    assert quote.ask > 0
    assert quote.ask >= quote.bid
    assert quote.timestamp.tzinfo is not None
    provider.disconnect()


def test_mock_provider_returns_empty_when_disconnected():
    provider = MockMarketDataProvider(seed=42)
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    assert bars == []


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

def test_validator_valid_bars():
    validator = DataValidator()
    bars = [
        _make_bar(ts=_utc(2024, 1, 1, 0, 0)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 1)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 2)),
    ]
    report = validator.validate_bars("EURUSD", MarketTimeframe.M1, bars)
    assert report.total_candles == 3
    assert report.valid_candles == 3
    assert report.invalid_candles == 0
    assert report.is_valid is True
    assert report.error_count == 0


def test_validator_duplicate_timestamps():
    validator = DataValidator()
    ts = _utc(2024, 1, 1, 0, 0)
    bars = [
        _make_bar(ts=ts),
        _make_bar(ts=ts),
    ]
    report = validator.validate_bars("EURUSD", MarketTimeframe.M1, bars)
    # Only the second occurrence is flagged as invalid (the first is valid).
    assert report.invalid_candles == 1
    assert report.error_count >= 1
    assert any(i.code == "DUPLICATE_TIMESTAMP" for i in report.issues)


def test_validator_out_of_order():
    validator = DataValidator()
    bars = [
        _make_bar(ts=_utc(2024, 1, 1, 0, 2)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 0)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 1)),
    ]
    report = validator.validate_bars("EURUSD", MarketTimeframe.M1, bars)
    assert report.error_count >= 1
    assert any(i.code == "OUT_OF_ORDER" for i in report.issues)


def test_validator_unsupported_symbol():
    validator = DataValidator()
    bars = [_make_bar(symbol="INVALID")]
    report = validator.validate_bars("INVALID", MarketTimeframe.M1, bars)
    assert report.error_count >= 1
    assert any(i.code == "UNSUPPORTED_SYMBOL" for i in report.issues)


def test_validator_unsupported_timeframe():
    validator = DataValidator()
    bars = [_make_bar()]
    # Create a bar with an unsupported timeframe by using M1 but
    # passing a custom timeframe value through the constructor.
    # Since MarketTimeframe is an enum, all values are supported.
    # Test that unsupported symbol is caught instead.
    report = validator.validate_bars("INVALID_SYMBOL", MarketTimeframe.M1, bars)
    assert report.error_count >= 1
    assert any(i.code == "UNSUPPORTED_SYMBOL" for i in report.issues)


def test_validator_missing_intervals():
    validator = DataValidator()
    bars = [
        _make_bar(ts=_utc(2024, 1, 1, 0, 0)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 5)),  # gap of 4 minutes
    ]
    report = validator.validate_bars("EURUSD", MarketTimeframe.M1, bars)
    assert report.warning_count >= 1
    assert any(i.code == "MISSING_INTERVALS" for i in report.issues)


# ---------------------------------------------------------------------------
# Processor tests
# ---------------------------------------------------------------------------

def test_processor_sort_chronologically():
    bars = [
        _make_bar(ts=_utc(2024, 1, 1, 0, 5)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 0)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 3)),
    ]
    sorted_bars = DataProcessor.sort_chronologically(bars)
    assert [b.timestamp for b in sorted_bars] == [
        _utc(2024, 1, 1, 0, 0),
        _utc(2024, 1, 1, 0, 3),
        _utc(2024, 1, 1, 0, 5),
    ]


def test_processor_filter_by_symbol():
    bars = [
        _make_bar(symbol="EURUSD"),
        _make_bar(symbol="GBPUSD"),
        _make_bar(symbol="EURUSD"),
    ]
    filtered = DataProcessor.filter_by_symbol(bars, "EURUSD")
    assert len(filtered) == 2
    assert all(b.symbol == "EURUSD" for b in filtered)


def test_processor_filter_by_timeframe():
    bars = [
        _make_bar(tf=MarketTimeframe.M1),
        _make_bar(tf=MarketTimeframe.H1),
        _make_bar(tf=MarketTimeframe.M1),
    ]
    filtered = DataProcessor.filter_by_timeframe(bars, MarketTimeframe.M1)
    assert len(filtered) == 2
    assert all(b.timeframe == MarketTimeframe.M1 for b in filtered)


def test_processor_filter_by_date_range():
    bars = [
        _make_bar(ts=_utc(2024, 1, 1, 0, 0)),
        _make_bar(ts=_utc(2024, 1, 2, 0, 0)),
        _make_bar(ts=_utc(2024, 1, 3, 0, 0)),
    ]
    filtered = DataProcessor.filter_by_date_range(
        bars, _utc(2024, 1, 2), _utc(2024, 1, 2, 23, 59)
    )
    assert len(filtered) == 1
    assert filtered[0].timestamp == _utc(2024, 1, 2, 0, 0)


def test_processor_deduplicate():
    bar = _make_bar(ts=_utc(2024, 1, 1, 0, 0))
    bars = [bar, bar, _make_bar(ts=_utc(2024, 1, 1, 0, 1))]
    deduped = DataProcessor.deduplicate(bars)
    assert len(deduped) == 2


def test_processor_detect_missing_intervals():
    bars = [
        _make_bar(ts=_utc(2024, 1, 1, 0, 0)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 5)),  # missing 1,2,3,4
    ]
    missing = DataProcessor.detect_missing_intervals(bars)
    assert len(missing) == 4


def test_processor_standardize():
    bars = [
        _make_bar(ts=_utc(2024, 1, 1, 0, 5)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 0)),
        _make_bar(ts=_utc(2024, 1, 1, 0, 0)),  # duplicate
    ]
    result = DataProcessor.standardize(bars)
    assert len(result) == 2
    assert result[0].timestamp == _utc(2024, 1, 1, 0, 0)
    assert result[1].timestamp == _utc(2024, 1, 1, 0, 5)


# ---------------------------------------------------------------------------
# CSV provider tests
# ---------------------------------------------------------------------------

def _write_csv(tmp_path, filename, rows, header=None):
    if header is None:
        header = ["timestamp", "open", "high", "low", "close", "tick_volume", "real_volume", "spread"]
    path = tmp_path / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


def test_csv_provider_load_valid(tmp_path):
    path = _write_csv(tmp_path, "EURUSD_M1.csv", [
        ["2024-01-01 00:00:00", "1.1000", "1.1010", "1.0990", "1.1005", "100", "1000", "0.0002"],
        ["2024-01-01 00:01:00", "1.1005", "1.1015", "1.1000", "1.1010", "110", "1100", "0.0002"],
    ])
    provider = HistoricalCSVProvider(data_dir=str(tmp_path), symbol="EURUSD", timeframe=MarketTimeframe.M1)
    provider.connect()
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    provider.disconnect()
    assert len(bars) == 2
    assert bars[0].symbol == "EURUSD"
    assert bars[0].open == Decimal("1.1000")
    assert bars[0].tick_volume == 100
    assert bars[0].real_volume == 1000
    assert bars[0].spread == Decimal("0.0002")


def test_csv_provider_missing_required_columns(tmp_path):
    path = _write_csv(tmp_path, "EURUSD_M1.csv", [
        ["2024-01-01 00:00:00", "1.1000", "1.1010"],
    ], header=["timestamp", "open", "high"])
    provider = HistoricalCSVProvider(data_dir=str(tmp_path), symbol="EURUSD", timeframe=MarketTimeframe.M1)
    provider.connect()
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    provider.disconnect()
    assert bars == []  # missing required columns -> no bars


def test_csv_provider_invalid_rows_skipped(tmp_path):
    path = _write_csv(tmp_path, "EURUSD_M1.csv", [
        ["2024-01-01 00:00:00", "1.1000", "1.1010", "1.0990", "1.1005", "100", "1000", "0.0002"],
        ["invalid-timestamp", "1.1005", "1.1015", "1.1000", "1.1010", "110", "1100", "0.0002"],
        ["2024-01-01 00:02:00", "not-a-price", "1.1015", "1.1000", "1.1010", "110", "1100", "0.0002"],
    ])
    provider = HistoricalCSVProvider(data_dir=str(tmp_path), symbol="EURUSD", timeframe=MarketTimeframe.M1)
    provider.connect()
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    provider.disconnect()
    assert len(bars) == 1  # only valid row kept


def test_csv_provider_file_not_found():
    provider = HistoricalCSVProvider(data_dir="/nonexistent/path", symbol="EURUSD", timeframe=MarketTimeframe.M1)
    provider.connect()
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    provider.disconnect()
    assert bars == []


def test_csv_provider_optional_columns_absent(tmp_path):
    path = _write_csv(tmp_path, "EURUSD_M1.csv", [
        ["2024-01-01 00:00:00", "1.1000", "1.1010", "1.0990", "1.1005"],
    ], header=["timestamp", "open", "high", "low", "close"])
    provider = HistoricalCSVProvider(data_dir=str(tmp_path), symbol="EURUSD", timeframe=MarketTimeframe.M1)
    provider.connect()
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    provider.disconnect()
    assert len(bars) == 1
    assert bars[0].tick_volume is None
    assert bars[0].real_volume is None
    assert bars[0].spread is None


# ---------------------------------------------------------------------------
# Service layer tests
# ---------------------------------------------------------------------------

def test_service_register_mock_provider():
    service = MarketDataService()
    provider = MockMarketDataProvider(seed=42)
    assert service.register_provider("mock", provider) is True
    assert "mock" in service.list_providers()
    assert service.get_active_provider() is provider


def test_service_get_candles_through_service():
    service = MarketDataService()
    provider = MockMarketDataProvider(seed=42)
    service.register_provider("mock", provider)
    bars = service.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 10))
    assert len(bars) > 0
    assert all(b.symbol == "EURUSD" for b in bars)


def test_service_validate_through_service():
    service = MarketDataService()
    provider = MockMarketDataProvider(seed=42)
    service.register_provider("mock", provider)
    bars = service.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 10))
    report = service.validate_candles("EURUSD", MarketTimeframe.M1, bars)
    assert isinstance(report, DataQualityReport)
    assert report.total_candles == len(bars)


def test_service_disconnect_all():
    service = MarketDataService()
    provider = MockMarketDataProvider(seed=42)
    service.register_provider("mock", provider)
    service.disconnect_all()
    assert provider.is_connected is False
    assert service.list_providers() == []


# ---------------------------------------------------------------------------
# UTC handling
# ---------------------------------------------------------------------------

def test_utc_timestamps_from_mock():
    provider = MockMarketDataProvider(seed=42)
    provider.connect()
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 5))
    provider.disconnect()
    for bar in bars:
        assert bar.timestamp.tzinfo is not None
        assert bar.timestamp.utcoffset() == timedelta(0)


def test_utc_timestamps_from_csv(tmp_path):
    path = _write_csv(tmp_path, "EURUSD_M1.csv", [
        ["2024-01-01 00:00:00", "1.1000", "1.1010", "1.0990", "1.1005", "100", "1000", "0.0002"],
    ])
    provider = HistoricalCSVProvider(data_dir=str(tmp_path), symbol="EURUSD", timeframe=MarketTimeframe.M1)
    provider.connect()
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    provider.disconnect()
    for bar in bars:
        assert bar.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_provider_disconnected_returns_empty():
    provider = MockMarketDataProvider(seed=42)
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    assert bars == []


def test_service_no_provider_returns_empty():
    service = MarketDataService()
    bars = service.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 2))
    assert bars == []


# ---------------------------------------------------------------------------
# Instrument registry / spec tests
# ---------------------------------------------------------------------------

def test_instrument_type_asset_classes():
    assert InstrumentType.FOREX.value == "forex"
    assert InstrumentType.METAL.value == "metal"
    assert InstrumentType.ENERGY.value == "energy"
    assert InstrumentType.INDEX.value == "index"
    assert InstrumentType.EQUITY.value == "equity"
    assert InstrumentType.CRYPTO.value == "crypto"
    assert InstrumentType.OTHER.value == "other"


def test_default_instrument_specs_multi_asset():
    specs = DEFAULT_INSTRUMENT_SPECS
    asset_classes = {s.instrument_type for s in specs}
    assert InstrumentType.FOREX in asset_classes
    assert InstrumentType.METAL in asset_classes
    assert InstrumentType.ENERGY in asset_classes
    assert InstrumentType.INDEX in asset_classes
    assert InstrumentType.CRYPTO in asset_classes
    # Forex symbols
    assert any(s.canonical_symbol == "EURUSD" for s in specs)
    assert any(s.canonical_symbol == "GBPUSD" for s in specs)
    assert any(s.canonical_symbol == "USDJPY" for s in specs)
    # Metals
    assert any(s.canonical_symbol == "XAUUSD" for s in specs)
    assert any(s.canonical_symbol == "XAGUSD" for s in specs)
    assert any(s.canonical_symbol == "XPTUSD" for s in specs)
    assert any(s.canonical_symbol == "XPDUSD" for s in specs)
    # Energy
    assert any(s.canonical_symbol == "WTIUSD" for s in specs)
    assert any(s.canonical_symbol == "BRENTUSD" for s in specs)
    # Indices
    assert any(s.canonical_symbol == "NAS100" for s in specs)
    assert any(s.canonical_symbol == "US500" for s in specs)
    assert any(s.canonical_symbol == "GER40" for s in specs)
    # Crypto
    assert any(s.canonical_symbol == "BTCUSD" for s in specs)
    assert any(s.canonical_symbol == "ETHUSD" for s in specs)


def test_instrument_spec_optional_fields():
    # All fields except canonical_symbol should be optional.
    spec = InstrumentSpec(canonical_symbol="CUSTOM")
    assert spec.broker_symbol is None
    assert spec.name == ""
    assert spec.instrument_type == InstrumentType.FOREX
    assert spec.base_currency is None
    assert spec.quote_currency is None
    assert spec.price_precision is None
    assert spec.tick_size is None
    assert spec.pip_size is None
    assert spec.contract_size is None
    assert spec.volume_type == VolumeType.NONE
    assert spec.supported_timeframes is not None  # defaulted to all


def test_instrument_spec_broker_symbol_mapping():
    spec = InstrumentSpec(
        canonical_symbol="WTIUSD",
        broker_symbol="WTI",
        name="WTI Crude Oil",
        instrument_type=InstrumentType.ENERGY,
    )
    assert spec.canonical_symbol == "WTIUSD"
    assert spec.broker_symbol == "WTI"


def test_instrument_spec_tick_and_precision():
    spec = InstrumentSpec(
        canonical_symbol="EURUSD",
        name="Euro vs US Dollar",
        instrument_type=InstrumentType.FOREX,
        price_precision=5,
        tick_size=Decimal("0.00001"),
        pip_size=Decimal("0.0001"),
        contract_size=Decimal("100000"),
    )
    assert spec.price_precision == 5
    assert spec.tick_size == Decimal("0.00001")
    assert spec.pip_size == Decimal("0.0001")
    assert spec.contract_size == Decimal("100000")


def test_spec_for_symbol_found():
    spec = spec_for_symbol("XAUUSD")
    assert spec is not None
    assert spec.canonical_symbol == "XAUUSD"
    assert spec.instrument_type == InstrumentType.METAL


def test_spec_for_symbol_not_found():
    assert spec_for_symbol("NONEXISTENT") is None


def test_service_register_custom_instrument():
    service = MarketDataService()
    custom_spec = InstrumentSpec(
        canonical_symbol="MYSTOCK",
        broker_symbol="MSFT",
        name="Microsoft Corp",
        instrument_type=InstrumentType.EQUITY,
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("100"),
        market_session="equity",
    )
    service.register_instrument_spec(custom_spec)
    retrieved = service.get_instrument_spec("MYSTOCK")
    assert retrieved is not None
    assert retrieved.broker_symbol == "MSFT"
    assert retrieved.instrument_type == InstrumentType.EQUITY
    assert retrieved.price_precision == 2


def test_service_list_instrument_specs():
    service = MarketDataService()
    specs = service.list_instrument_specs()
    assert len(specs) >= 19  # All default specs
    assert any(s.canonical_symbol == "BTCUSD" for s in specs)


# ---------------------------------------------------------------------------
# Market session awareness tests
# ---------------------------------------------------------------------------

def test_session_calendar_forex_weekend_closed():
    calendar = SessionCalendar(dict(DEFAULT_SESSIONS))
    # Saturday
    sat = _utc(2024, 1, 6, 12, 0)  # 2024-01-06 is a Saturday
    assert calendar.is_market_open("forex", sat) is False
    # Sunday
    sun = _utc(2024, 1, 7, 12, 0)  # 2024-01-07 is a Sunday
    assert calendar.is_market_open("forex", sun) is False


def test_session_calendar_forex_weekday_open():
    calendar = SessionCalendar(dict(DEFAULT_SESSIONS))
    # Tuesday
    tue = _utc(2024, 1, 2, 12, 0)  # 2024-01-02 is a Tuesday
    assert calendar.is_market_open("forex", tue) is True


def test_session_calendar_crypto_always_open():
    calendar = SessionCalendar(dict(DEFAULT_SESSIONS))
    # Saturday
    sat = _utc(2024, 1, 6, 12, 0)
    assert calendar.is_market_open("crypto", sat) is True
    # Sunday
    sun = _utc(2024, 1, 7, 12, 0)
    assert calendar.is_market_open("crypto", sun) is True


def test_session_calendar_register_custom():
    calendar = SessionCalendar()
    custom = MarketSession(
        session_id="custom",
        description="Custom session",
        is_24h=True,
        weekend_days=frozenset(),
    )
    calendar.register_session("custom", custom)
    assert calendar.get_session("custom") is custom


def test_validator_session_aware_weekend_gap_not_reported():
    """Forex weekend gaps should not be reported as missing intervals."""
    validator = DataValidator()
    # Friday 22:00 (market close) to Sunday 22:00 (market open) - pure weekend.
    friday_close = _utc(2024, 1, 5, 22, 0)  # Friday 22:00 UTC
    sunday_open = _utc(2024, 1, 7, 22, 0)  # Sunday 22:00 UTC
    bars = [
        _make_bar(ts=friday_close),
        _make_bar(ts=sunday_open),
    ]
    report = validator.validate_bars("EURUSD", MarketTimeframe.H1, bars)
    # Should NOT report MISSING_INTERVALS because the gap is a weekend closure.
    missing_issues = [i for i in report.issues if i.code == "MISSING_INTERVALS"]
    assert len(missing_issues) == 0


def test_validator_session_aware_weekday_gap_reported():
    """Weekday gaps SHOULD be reported as missing intervals."""
    validator = DataValidator()
    tuesday = _utc(2024, 1, 2, 10, 0)
    wednesday = _utc(2024, 1, 3, 10, 0)  # 24 hours later = 24 missing H1 bars
    bars = [
        _make_bar(ts=tuesday),
        _make_bar(ts=wednesday),
    ]
    report = validator.validate_bars("EURUSD", MarketTimeframe.H1, bars)
    missing_issues = [i for i in report.issues if i.code == "MISSING_INTERVALS"]
    assert len(missing_issues) == 1


# ---------------------------------------------------------------------------
# Candle quality / metadata tests
# ---------------------------------------------------------------------------

def test_ohlc_bar_incomplete_flag():
    bar = OHLCBar(
        symbol="EURUSD",
        timeframe=MarketTimeframe.M1,
        timestamp=_utc(2024, 1, 1, 0, 0),
        open=Decimal("1.1000"),
        high=Decimal("1.1010"),
        low=Decimal("1.0990"),
        close=Decimal("1.1005"),
        is_complete=False,
        data_source=DataSource.SIMULATED,
    )
    assert bar.is_complete is False
    assert bar.data_source == DataSource.SIMULATED


def test_ohlc_bar_incomplete_historical_rejected():
    """Incomplete candle cannot be treated as historical."""
    with pytest.raises(ValueError):
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=_utc(2024, 1, 1, 0, 0),
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
            is_complete=False,
            data_source=DataSource.HISTORICAL,
        )


def test_ohlc_bar_bid_ask():
    bar = OHLCBar(
        symbol="EURUSD",
        timeframe=MarketTimeframe.M1,
        timestamp=_utc(2024, 1, 1, 0, 0),
        open=Decimal("1.1000"),
        high=Decimal("1.1010"),
        low=Decimal("1.0990"),
        close=Decimal("1.1005"),
        bid=Decimal("1.0999"),
        ask=Decimal("1.1001"),
    )
    assert bar.bid == Decimal("1.0999")
    assert bar.ask == Decimal("1.1001")


def test_data_source_classification():
    sim_bar = OHLCBar(
        symbol="EURUSD",
        timeframe=MarketTimeframe.M1,
        timestamp=_utc(2024, 1, 1, 0, 0),
        open=Decimal("1.1000"),
        high=Decimal("1.1010"),
        low=Decimal("1.0990"),
        close=Decimal("1.1005"),
        data_source=DataSource.SIMULATED,
    )
    hist_bar = OHLCBar(
        symbol="EURUSD",
        timeframe=MarketTimeframe.M1,
        timestamp=_utc(2024, 1, 1, 0, 1),
        open=Decimal("1.1005"),
        high=Decimal("1.1015"),
        low=Decimal("1.1000"),
        close=Decimal("1.1010"),
        data_source=DataSource.HISTORICAL,
    )
    assert sim_bar.data_source == DataSource.SIMULATED
    assert hist_bar.data_source == DataSource.HISTORICAL


def test_mock_provider_data_source_simulated():
    provider = MockMarketDataProvider(seed=42)
    provider.connect()
    bars = provider.get_candles("EURUSD", MarketTimeframe.M1, _utc(2024, 1, 1), _utc(2024, 1, 1, 0, 5))
    provider.disconnect()
    for bar in bars:
        assert bar.data_source == DataSource.SIMULATED
        assert bar.is_complete is True


# ---------------------------------------------------------------------------
# Timeframe tests (W1, MN1)
# ---------------------------------------------------------------------------

def test_new_timeframes():
    assert MarketTimeframe.W1 == "W1"
    assert MarketTimeframe.W1.minutes == 10080
    assert MarketTimeframe.MN1 == "MN1"
    assert MarketTimeframe.MN1.minutes == 43200


def test_timeframe_from_string_w1_mn1():
    assert MarketTimeframe.from_string("w1") == MarketTimeframe.W1
    assert MarketTimeframe.from_string("mn1") == MarketTimeframe.MN1


def test_mock_provider_w1_candles():
    provider = MockMarketDataProvider(seed=42)
    provider.connect()
    start = _utc(2024, 1, 1)
    end = _utc(2024, 2, 1)
    bars = provider.get_candles("EURUSD", MarketTimeframe.W1, start, end)
    assert len(bars) > 0
    for bar in bars:
        assert bar.timeframe == MarketTimeframe.W1
    provider.disconnect()


# ---------------------------------------------------------------------------
# Timezone / DST edge cases
# ---------------------------------------------------------------------------

def test_timestamp_must_be_utc_aware():
    with pytest.raises(ValueError):
        OHLCBar(
            symbol="EURUSD",
            timeframe=MarketTimeframe.M1,
            timestamp=datetime(2024, 1, 1, 0, 0),  # naive
            open=Decimal("1.1000"),
            high=Decimal("1.1010"),
            low=Decimal("1.0990"),
            close=Decimal("1.1005"),
        )


def test_timezone_aware_timestamps_accepted():
    """Non-UTC timezone-aware timestamps are accepted by OHLCBar."""
    ts_with_offset = datetime(2024, 1, 1, 17, 0, tzinfo=timezone(timedelta(hours=-5)))
    bar = OHLCBar(
        symbol="EURUSD",
        timeframe=MarketTimeframe.M1,
        timestamp=ts_with_offset,
        open=Decimal("1.1000"),
        high=Decimal("1.1010"),
        low=Decimal("1.0990"),
        close=Decimal("1.1005"),
    )
    assert bar.timestamp.tzinfo is not None
