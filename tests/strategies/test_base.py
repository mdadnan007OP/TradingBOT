"""Tests for the Strategy Engine base module (signal model and interfaces)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalStatus,
)


class TestSignalDirection:
    def test_values(self):
        assert SignalDirection.LONG == "LONG"
        assert SignalDirection.SHORT == "SHORT"
        assert SignalDirection.NONE == "NONE"

    def test_is_str_enum(self):
        assert SignalDirection.LONG.value == "LONG"
        assert SignalDirection.SHORT.value == "SHORT"
        assert SignalDirection.NONE.value == "NONE"


class TestSignalStatus:
    def test_values(self):
        assert SignalStatus.ACTIVE == "ACTIVE"
        assert SignalStatus.EXPIRED == "EXPIRED"
        assert SignalStatus.REJECTED == "REJECTED"
        assert SignalStatus.NO_SIGNAL == "NO_SIGNAL"


class TestMarketRegime:
    def test_values(self):
        assert MarketRegime.TRENDING == "TRENDING"
        assert MarketRegime.RANGING == "RANGING"
        assert MarketRegime.HIGH_VOLATILITY == "HIGH_VOLATILITY"
        assert MarketRegime.LOW_VOLATILITY == "LOW_VOLATILITY"
        assert MarketRegime.TRANSITIONING == "TRANSITIONING"
        assert MarketRegime.UNKNOWN == "UNKNOWN"


class TestSignal:
    def test_create_signal(self):
        sig = Signal(
            signal_id="sig-1",
            strategy_name="TestStrategy",
            strategy_version="1.0.0",
            symbol="EURUSD",
            instrument_type="forex",
            direction=SignalDirection.LONG,
            status=SignalStatus.ACTIVE,
            entry_timeframe=__import__(
                "src.market_data.models", fromlist=["MarketTimeframe"]
            ).MarketTimeframe.H1,
            confirmation_timeframes=[],
            signal_timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            market_data_timestamp=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
            reference_price=Decimal("100.50"),
            technical_invalidation=Decimal("99.00"),
            parameters=__import__(
                "src.indicators.base", fromlist=["IndicatorParameters"]
            ).IndicatorParameters(values={"ema_fast": 9}),
            indicator_snapshot={"ema_9": [Decimal("100"), Decimal("100.5")]},
            market_regime=MarketRegime.TRENDING,
            confirmation_conditions=["EMA bullish", "ADX > 25"],
            explanation="EMA 9 > EMA 21, ADX trending",
            expiry_conditions=["EMA crossover"],
            data_source=__import__(
                "src.market_data.models", fromlist=["DataSource"]
            ).DataSource.SIMULATED,
            strategy_validity_state="valid",
        )
        assert sig.signal_id == "sig-1"
        assert sig.strategy_name == "TestStrategy"
        assert sig.direction == SignalDirection.LONG
        assert sig.status == SignalStatus.ACTIVE
        assert sig.reference_price == Decimal("100.50")
        assert sig.technical_invalidation == Decimal("99.00")
        assert sig.market_regime == MarketRegime.TRENDING
        assert sig.explanation == "EMA 9 > EMA 21, ADX trending"

    def test_signal_defaults(self):
        MTF = __import__(
            "src.market_data.models", fromlist=["MarketTimeframe"]
        ).MarketTimeframe
        DS = __import__(
            "src.market_data.models", fromlist=["DataSource"]
        ).DataSource
        IP = __import__(
            "src.indicators.base", fromlist=["IndicatorParameters"]
        ).IndicatorParameters

        sig = Signal(
            signal_id="s1",
            strategy_name="S",
            strategy_version="1.0",
            symbol="XAUUSD",
            instrument_type="metal",
            direction=SignalDirection.NONE,
            status=SignalStatus.NO_SIGNAL,
            entry_timeframe=MTF.M15,
            confirmation_timeframes=[],
            signal_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            market_data_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_price=None,
            technical_invalidation=None,
            parameters=IP(),
            indicator_snapshot={},
            market_regime=MarketRegime.UNKNOWN,
            confirmation_conditions=[],
            explanation="No signal",
            expiry_conditions=[],
            data_source=DS.SIMULATED,
            strategy_validity_state="valid",
        )
        assert sig.reference_price is None
        assert sig.technical_invalidation is None
        assert sig.metadata == {}
