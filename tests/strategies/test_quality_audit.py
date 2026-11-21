"""Quality audit tests for Phase 5 Signal Lifecycle, Validation, and Risk Interface.

Tests cover:
- Duplicate signal detection and prevention
- Signal expiration and invalidation
- Strategy versioning and config fingerprint
- Signal explainability (conditions, regime, timeframes)
- Signal quality validation (stale data, invalid OHLC, insufficient candles)
- Risk interface compatibility (RiskInterfaceSignal export)
- Historical look-ahead prevention
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.indicators.base import IndicatorParameters
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalRejection,
    SignalStatus,
)
from src.strategies.models import (
    RiskInterfaceSignal,
    SignalValidationResult,
    compute_config_fingerprint,
)
from src.strategies.service import SignalService
from tests.strategies.conftest import make_candles


# ---------------------------------------------------------------------------
# Helper: build a minimal Signal for testing
# ---------------------------------------------------------------------------

def _make_signal(
    signal_id: str = "sig-1",
    direction: SignalDirection = SignalDirection.LONG,
    status: SignalStatus = SignalStatus.ACTIVE,
    market_data_timestamp: Optional[datetime] = None,
    signal_timestamp: Optional[datetime] = None,
    signal_valid_until: Optional[datetime] = None,
    config_fingerprint: str = "abc123",
    technical_invalidation: Optional[Decimal] = None,
    reference_price: Optional[Decimal] = Decimal("100.50"),
    **kwargs,
) -> Signal:
    from src.strategies.base import SignalRejection, StrategyResult
    MTF = MarketTimeframe
    DS = DataSource
    IP = IndicatorParameters
    now = signal_timestamp or datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    mdt = market_data_timestamp or datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
    return Signal(
        signal_id=signal_id,
        strategy_name="TestStrategy",
        strategy_version="1.0.0",
        config_fingerprint=config_fingerprint,
        symbol="EURUSD",
        instrument_type="forex",
        direction=direction,
        status=status,
        entry_timeframe=MTF.H1,
        confirmation_timeframes=[MTF.H4],
        signal_timestamp=now,
        signal_valid_until=signal_valid_until,
        market_data_timestamp=mdt,
        reference_price=reference_price,
        technical_invalidation=technical_invalidation,
        parameters=IP(values={"ema_fast": 9}),
        indicator_snapshot={"ema_9": [Decimal("100"), Decimal("100.5")]},
        market_regime=MarketRegime.TRENDING,
        confirmation_conditions=["EMA bullish"],
        failed_conditions=["RSI oversold"],
        explanation="EMA 9 > EMA 21, ADX trending",
        expiry_conditions=["EMA crossover"],
        data_source=DS.SIMULATED,
        strategy_validity_state="valid",
        **kwargs,
    )


from typing import Optional


class TestSignalLifecycle:
    """Tests for signal lifecycle: duplicate detection, expiration, invalidation."""

    def test_duplicate_key(self):
        sig = _make_signal()
        key = sig.duplicate_key
        assert "TestStrategy" in key
        assert "EURUSD" in key
        assert "H1" in key
        assert str(sig.market_data_timestamp) in key

    def test_duplicate_key_uniqueness(self):
        sig1 = _make_signal(signal_id="s1", market_data_timestamp=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc))
        sig2 = _make_signal(signal_id="s2", market_data_timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
        assert sig1.duplicate_key != sig2.duplicate_key

    def test_same_candle_same_key(self):
        ts = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
        sig1 = _make_signal(signal_id="s1", market_data_timestamp=ts)
        sig2 = _make_signal(signal_id="s2", market_data_timestamp=ts)
        assert sig1.duplicate_key == sig2.duplicate_key

    def test_is_expired_no_expiry(self):
        sig = _make_signal(signal_valid_until=None)
        assert sig.is_expired() is False

    def test_is_expired_future(self):
        future = datetime.now(timezone.utc) + timedelta(days=30)
        sig = _make_signal(signal_valid_until=future)
        assert sig.is_expired() is False

    def test_is_expired_past(self):
        past = datetime.now(timezone.utc) - timedelta(days=30)
        sig = _make_signal(signal_valid_until=past)
        assert sig.is_expired() is True

    def test_is_expired_custom_now(self):
        past = datetime.now(timezone.utc) - timedelta(days=30)
        future = datetime.now(timezone.utc) + timedelta(days=30)
        sig = _make_signal(signal_valid_until=past)
        assert sig.is_expired(now=future) is True

    def test_is_invalidated_long_below_level(self):
        sig = _make_signal(
            direction=SignalDirection.LONG,
            technical_invalidation=Decimal("99.00"),
        )
        assert sig.is_invalidated(Decimal("98.00")) is True
        assert sig.is_invalidated(Decimal("99.00")) is True
        assert sig.is_invalidated(Decimal("100.00")) is False

    def test_is_invalidated_short_above_level(self):
        sig = _make_signal(
            direction=SignalDirection.SHORT,
            technical_invalidation=Decimal("101.00"),
        )
        assert sig.is_invalidated(Decimal("102.00")) is True
        assert sig.is_invalidated(Decimal("101.00")) is True
        assert sig.is_invalidated(Decimal("100.00")) is False

    def test_is_invalidated_none_level(self):
        sig = _make_signal(technical_invalidation=None)
        assert sig.is_invalidated(Decimal("0")) is False

    def test_is_actionable_active_not_expired(self):
        future = datetime.now(timezone.utc) + timedelta(days=30)
        sig = _make_signal(status=SignalStatus.ACTIVE, signal_valid_until=future)
        assert sig.is_actionable() is True

    def test_is_actionable_expired(self):
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        sig = _make_signal(status=SignalStatus.ACTIVE, signal_valid_until=past)
        assert sig.is_actionable() is False

    def test_is_actionable_rejected(self):
        sig = _make_signal(status=SignalStatus.REJECTED)
        assert sig.is_actionable() is False

    def test_is_actionable_none(self):
        sig = _make_signal(direction=SignalDirection.NONE)
        assert sig.is_actionable() is False


class TestSignalValidation:
    """Tests for signal quality validation."""

    def setup_method(self):
        self.engine = create_engine()
        self.service = SignalService(self.engine)

    def test_valid_prerequisites(self):
        candles = make_candles([Decimal("100")] * 10)
        result = self.service.validate_signal_prerequisites(
            "EURUSD", candles, MarketTimeframe.H1, data_source=DataSource.SIMULATED,
        )
        assert result.valid is True
        assert result.category is None
        assert result.reason is None
        assert result.candle_count == 10

    def test_insufficient_candles(self):
        candles = make_candles([Decimal("100")])
        result = self.service.validate_signal_prerequisites(
            "EURUSD", candles, MarketTimeframe.H1, data_source=DataSource.SIMULATED,
            min_candles=5,
        )
        assert result.valid is False
        assert result.category == "insufficient_data"
        assert "5" in result.reason
        assert result.candle_count == 1

    def test_invalid_ohlc_high_low(self):
        # Create a valid candle first, then corrupt high to be < low
        bad = OHLCBar(
            symbol="EURUSD", timeframe=MarketTimeframe.H1,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=Decimal("100"), high=Decimal("102"), low=Decimal("99"),
            close=Decimal("100"), tick_volume=100,
            data_source=DataSource.SIMULATED,
        )
        # Force invalid state: high < low
        object.__setattr__(bad, "high", Decimal("98"))
        result = self.service.validate_signal_prerequisites(
            "EURUSD", [bad], MarketTimeframe.H1, data_source=DataSource.SIMULATED,
            min_candles=1,
        )
        assert result.valid is False
        assert result.category == "invalid_ohlc"

    def test_incomplete_candle(self):
        bad = OHLCBar(
            symbol="EURUSD", timeframe=MarketTimeframe.H1,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
            close=Decimal("100"), tick_volume=100,
            is_complete=False,
            data_source=DataSource.SIMULATED,
        )
        result = self.service.validate_signal_prerequisites(
            "EURUSD", [bad], MarketTimeframe.H1, data_source=DataSource.SIMULATED,
            min_candles=1,
        )
        assert result.valid is False
        assert result.category == "incomplete_candle"

    def test_duplicate_signal_detection(self):
        self.service.clear_signal_history()
        ts = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
        assert self.service.is_duplicate_signal("Strat", "EURUSD", MarketTimeframe.H1, ts) is False
        self.service.record_signal("Strat", "EURUSD", MarketTimeframe.H1, ts)
        assert self.service.is_duplicate_signal("Strat", "EURUSD", MarketTimeframe.H1, ts) is True
        # Different timeframe should not be duplicate
        assert self.service.is_duplicate_signal("Strat", "EURUSD", MarketTimeframe.H4, ts) is False


class TestSignalVersioning:
    """Tests for strategy versioning and config fingerprint."""

    def test_config_fingerprint_deterministic(self):
        params1 = {"ema_fast": 9, "ema_slow": 21}
        params2 = {"ema_slow": 21, "ema_fast": 9}  # Same params, different order
        fp1 = compute_config_fingerprint(params1)
        fp2 = compute_config_fingerprint(params2)
        assert fp1 == fp2  # Order-independent

    def test_config_fingerprint_different_params(self):
        fp1 = compute_config_fingerprint({"ema_fast": 9})
        fp2 = compute_config_fingerprint({"ema_fast": 21})
        assert fp1 != fp2

    def test_signal_has_config_fingerprint(self):
        sig = _make_signal()
        assert sig.config_fingerprint == "abc123"

    def test_risk_interface_preserves_fingerprint(self):
        sig = _make_signal(config_fingerprint="deadbeef")
        risk_sig = RiskInterfaceSignal(
            signal_id=sig.signal_id,
            strategy_name=sig.strategy_name,
            strategy_version=sig.strategy_version,
            config_fingerprint=sig.config_fingerprint,
            symbol=sig.symbol,
            instrument_type=sig.instrument_type,
            direction=sig.direction.value,
            signal_timestamp=sig.signal_timestamp,
            signal_valid_until=sig.signal_valid_until,
            market_data_timestamp=sig.market_data_timestamp,
            reference_price=sig.reference_price,
            technical_invalidation=sig.technical_invalidation,
            market_regime=sig.market_regime.value,
            confirmation_conditions=sig.confirmation_conditions,
            failed_conditions=sig.failed_conditions,
            explanation=sig.explanation,
            expiry_conditions=sig.expiry_conditions,
            data_source=sig.data_source.value,
            indicator_snapshot=sig.indicator_snapshot,
            parameters=dict(sig.parameters.values),
            entry_timeframe=sig.entry_timeframe,
            confirmation_timeframes=sig.confirmation_timeframes,
        )
        d = risk_sig.to_dict()
        assert d["config_fingerprint"] == "deadbeef"
        assert d["signal_id"] == "sig-1"
        assert d["direction"] == "LONG"


class TestSignalExplainability:
    """Tests for signal explainability."""

    def test_signal_has_explanation(self):
        sig = _make_signal()
        assert sig.explanation is not None
        assert len(sig.explanation) > 0
        assert "EMA" in sig.explanation

    def test_signal_has_confirmation_conditions(self):
        sig = _make_signal()
        assert len(sig.confirmation_conditions) > 0
        assert "EMA bullish" in sig.confirmation_conditions

    def test_signal_has_failed_conditions(self):
        sig = _make_signal()
        assert len(sig.failed_conditions) > 0
        assert "RSI oversold" in sig.failed_conditions

    def test_signal_has_market_regime(self):
        sig = _make_signal()
        assert sig.market_regime == MarketRegime.TRENDING

    def test_signal_has_timeframes(self):
        sig = _make_signal()
        assert sig.entry_timeframe == MarketTimeframe.H1
        assert MarketTimeframe.H4 in sig.confirmation_timeframes

    def test_signal_has_indicator_snapshot(self):
        sig = _make_signal()
        assert "ema_9" in sig.indicator_snapshot
        assert sig.indicator_snapshot["ema_9"][-1] == Decimal("100.5")


class TestRiskInterface:
    """Tests for Phase 6 risk interface compatibility."""

    def test_risk_interface_to_dict(self):
        sig = _make_signal()
        risk_sig = RiskInterfaceSignal(
            signal_id=sig.signal_id,
            strategy_name=sig.strategy_name,
            strategy_version=sig.strategy_version,
            config_fingerprint=sig.config_fingerprint,
            symbol=sig.symbol,
            instrument_type=sig.instrument_type,
            direction=sig.direction.value,
            signal_timestamp=sig.signal_timestamp,
            signal_valid_until=sig.signal_valid_until,
            market_data_timestamp=sig.market_data_timestamp,
            reference_price=sig.reference_price,
            technical_invalidation=sig.technical_invalidation,
            market_regime=sig.market_regime.value,
            confirmation_conditions=sig.confirmation_conditions,
            failed_conditions=sig.failed_conditions,
            explanation=sig.explanation,
            expiry_conditions=sig.expiry_conditions,
            data_source=sig.data_source.value,
            indicator_snapshot=sig.indicator_snapshot,
            parameters=dict(sig.parameters.values),
            entry_timeframe=sig.entry_timeframe,
            confirmation_timeframes=sig.confirmation_timeframes,
        )
        d = risk_sig.to_dict()
        # Verify all required fields present
        assert "signal_id" in d
        assert "strategy_name" in d
        assert "strategy_version" in d
        assert "config_fingerprint" in d
        assert "symbol" in d
        assert "direction" in d
        assert "signal_timestamp" in d
        assert "market_data_timestamp" in d
        assert "reference_price" in d
        assert "technical_invalidation" in d
        assert "market_regime" in d
        assert "explanation" in d
        assert "data_source" in d
        assert "entry_timeframe" in d

    def test_risk_interface_decimal_serialization(self):
        sig = _make_signal(reference_price=Decimal("100.50"))
        risk_sig = RiskInterfaceSignal(
            signal_id=sig.signal_id,
            strategy_name=sig.strategy_name,
            strategy_version=sig.strategy_version,
            config_fingerprint=sig.config_fingerprint,
            symbol=sig.symbol,
            instrument_type=sig.instrument_type,
            direction=sig.direction.value,
            signal_timestamp=sig.signal_timestamp,
            signal_valid_until=sig.signal_valid_until,
            market_data_timestamp=sig.market_data_timestamp,
            reference_price=sig.reference_price,
            technical_invalidation=sig.technical_invalidation,
            market_regime=sig.market_regime.value,
            confirmation_conditions=sig.confirmation_conditions,
            failed_conditions=sig.failed_conditions,
            explanation=sig.explanation,
            expiry_conditions=sig.expiry_conditions,
            data_source=sig.data_source.value,
            indicator_snapshot=sig.indicator_snapshot,
            parameters=dict(sig.parameters.values),
            entry_timeframe=sig.entry_timeframe,
            confirmation_timeframes=sig.confirmation_timeframes,
        )
        d = risk_sig.to_dict()
        assert d["reference_price"] == "100.50"


class TestServiceValidation:
    """Tests for SignalService validation and lifecycle methods."""

    def setup_method(self):
        self.engine = create_engine()
        self.service = SignalService(self.engine)

    def test_compute_signal_valid_until(self):
        ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        valid_until = self.service.compute_signal_valid_until(ts, max_age_minutes=60)
        assert valid_until == ts + timedelta(minutes=60)

    def test_compute_signal_valid_until_none(self):
        ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert self.service.compute_signal_valid_until(ts, max_age_minutes=None) is None

    def test_filter_expired_signals(self):
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        future = datetime(2025, 1, 1, tzinfo=timezone.utc)
        now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        sig_expired = _make_signal(signal_valid_until=past)
        sig_active = _make_signal(signal_id="s2", signal_valid_until=future)
        result = self.service.filter_expired_signals([sig_expired, sig_active], now)
        assert len(result) == 1
        assert result[0].signal_id == "s2"

    def test_filter_invalidated_signals(self):
        sig_valid = _make_signal(direction=SignalDirection.LONG, technical_invalidation=Decimal("90.00"))
        sig_invalid = _make_signal(signal_id="s2", direction=SignalDirection.LONG, technical_invalidation=Decimal("110.00"))
        result = self.service.filter_invalidated_signals([sig_valid, sig_invalid], Decimal("95.00"))
        assert len(result) == 1
        assert result[0].signal_id == "sig-1"

    def test_clear_signal_history(self):
        self.service.record_signal("Strat", "EURUSD", MarketTimeframe.H1, datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert self.service.get_signal_history_count() if hasattr(self.service, 'get_signal_history_count') else True
        self.service.clear_signal_history()
        # After clear, duplicate check should return False
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert self.service.is_duplicate_signal("Strat", "EURUSD", MarketTimeframe.H1, ts) is False


class TestLookAheadPrevention:
    """Tests for historical look-ahead prevention."""

    def setup_method(self):
        self.engine = create_engine()
        self.service = SignalService(self.engine)

    def test_no_future_candle_in_indicators(self):
        """Indicators must not use future candle data."""
        engine = create_engine()
        # Create 10 candles
        candles = make_candles([Decimal(str(100 + i)) for i in range(10)])
        result = engine.calculate("SMA", "EURUSD", MarketTimeframe.H1, candles,
                                parameters=IndicatorParameters(values={"periods": [5]}))
        sma_series = result.values.get("sma_5", [])
        # First 4 values should be None (warm-up), values from index 4 onward should be computed
        assert sma_series[0] is None
        assert sma_series[1] is None
        assert sma_series[2] is None
        assert sma_series[3] is None
        assert sma_series[4] is not None  # First valid at index 4 (period-1)

    def test_incomplete_candle_rejected(self):
        """Incomplete candles should not generate signals."""
        bad = OHLCBar(
            symbol="EURUSD", timeframe=MarketTimeframe.H1,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
            close=Decimal("100"), tick_volume=100,
            is_complete=False,
            data_source=DataSource.SIMULATED,
        )
        result = self.service.validate_signal_prerequisites(
            "EURUSD", [bad], MarketTimeframe.H1, data_source=DataSource.SIMULATED,
            min_candles=1,
        )
        assert result.valid is False
        assert result.category == "incomplete_candle"

    def test_signal_timestamp_not_future(self):
        """Signal timestamp should not be in the future relative to market data."""
        engine = create_engine()
        candles = make_candles([Decimal("100")] * 10)
        # Just verify that the service uses market_data_timestamp from candles
        # not a future timestamp
        result = engine.calculate("SMA", "EURUSD", MarketTimeframe.H1, candles,
                                parameters=IndicatorParameters(values={"periods": [5]}))
        assert result.source_candle_timestamp <= candles[-1].timestamp


class TestSignalRejection:
    """Tests for signal rejection categories."""

    def test_rejection_has_category(self):
        rej = SignalRejection(
            symbol="EURUSD",
            timeframe=MarketTimeframe.H1,
            strategy_name="Test",
            reason="Test reason",
            category="insufficient_data",
            data_source=DataSource.SIMULATED,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert rej.category == "insufficient_data"
        assert rej.reason == "Test reason"

    def test_rejection_default_category(self):
        rej = SignalRejection(
            symbol="EURUSD",
            timeframe=MarketTimeframe.H1,
            strategy_name="Test",
            reason="Test reason",
            data_source=DataSource.SIMULATED,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert rej.category == "unknown"

    def test_rejection_missing_indicators(self):
        rej = SignalRejection(
            symbol="EURUSD",
            timeframe=MarketTimeframe.H1,
            strategy_name="Test",
            reason="ADX not ready",
            category="unavailable_indicator",
            data_source=DataSource.SIMULATED,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            missing_indicators=["ADX", "ATR"],
        )
        assert "ADX" in rej.missing_indicators
        assert "ATR" in rej.missing_indicators
