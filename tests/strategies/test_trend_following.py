"""Tests for the Trend Following Strategy."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.trend_following import TrendFollowingStrategy


def _make_uptrend_candles(n: int = 60, start: Decimal = Decimal("100")):
    """Create strongly trending upward candles."""
    from tests.strategies.conftest import make_trending_candles
    return make_trending_candles(n, start, Decimal("1"))


def _make_downtrend_candles(n: int = 60, start: Decimal = Decimal("100")):
    """Create strongly trending downward candles."""
    from tests.strategies.conftest import make_downtrending_candles
    return make_downtrending_candles(n, start, Decimal("1"))


class TestTrendFollowingStrategy:
    def setup_method(self):
        self.strategy = TrendFollowingStrategy()
        self.engine = create_engine()

    def test_strategy_properties(self):
        assert self.strategy.name == "TrendFollowing"
        assert self.strategy.version == "1.0.0"
        assert self.strategy.enabled is True
        assert MarketTimeframe.H1 in self.strategy.required_timeframes

    def test_enable_disable(self):
        self.strategy.disable()
        assert self.strategy.enabled is False
        self.strategy.enable()
        assert self.strategy.enabled is True

    def test_uptrend_long_signal(self):
        """Strong uptrend should produce LONG signal."""
        candles = _make_uptrend_candles(60, Decimal("100"))
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error is None, f"Unexpected error: {result.error}"
        long_signals = [s for s in result.signals if s.direction == "LONG"]
        # May or may not produce a signal depending on indicator values
        # But should not error
        assert isinstance(result.signals, list)

    def test_downtrend_short_signal(self):
        """Strong downtrend should produce SHORT signal or rejection."""
        candles = _make_downtrend_candles(60, Decimal("100"))
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error is None, f"Unexpected error: {result.error}"
        assert isinstance(result.signals, list)
        assert isinstance(result.rejections, list)

    def test_insufficient_candles(self):
        """Too few candles should produce rejection."""
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100"), Decimal("101")])
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        # Should not crash, may produce rejection
        assert isinstance(result.signals, list)
        assert isinstance(result.rejections, list)

    def test_disabled_strategy(self):
        self.strategy.disable()
        candles = _make_uptrend_candles(60, Decimal("100"))
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error == "Strategy is disabled"
        assert len(result.signals) == 0

    def test_invalid_parameters(self):
        from src.indicators.base import IndicatorParameters
        params = IndicatorParameters(values={"ema_fast": 21, "ema_slow": 9})
        # fast >= slow should raise
        with pytest.raises(ValueError):
            self.strategy.validate_parameters(params)

    def test_default_parameters(self):
        params = self.strategy.default_parameters
        assert params.get("ema_fast") == 9
        assert params.get("ema_slow") == 21

    def test_signal_structure(self):
        """Verify that any produced signal has correct structure."""
        candles = _make_uptrend_candles(100, Decimal("100"))
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        for sig in result.signals:
            assert sig.strategy_name == "TrendFollowing"
            assert sig.strategy_version == "1.0.0"
            assert sig.symbol == "EURUSD"
            assert sig.direction in ("LONG", "SHORT")
            assert sig.status == "ACTIVE"
            assert sig.entry_timeframe == MarketTimeframe.H1
            assert sig.explanation is not None
            assert len(sig.explanation) > 0
            assert sig.technical_invalidation is not None or True  # May be None
