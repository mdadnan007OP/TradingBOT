"""Tests for the Price Action Strategy."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.market_data.models import DataSource, MarketTimeframe
from src.strategies.price_action import PriceActionStrategy


def _make_candles_with_pattern(closes, timeframe=MarketTimeframe.M15):
    """Create candles from close prices."""
    from tests.strategies.conftest import make_candles
    return make_candles(closes, timeframe=timeframe)


class TestPriceActionStrategy:
    def setup_method(self):
        self.strategy = PriceActionStrategy()
        self.engine = create_engine()

    def test_strategy_properties(self):
        assert self.strategy.name == "PriceAction"
        assert self.strategy.version == "1.0.0"
        assert self.strategy.enabled is True

    def test_enable_disable(self):
        self.strategy.disable()
        assert self.strategy.enabled is False
        self.strategy.enable()
        assert self.strategy.enabled is True

    def test_bullish_engulfing_pattern(self):
        """Bearish candle followed by larger bullish candle that engulfs."""
        # Prior bearish: open=102, close=100
        # Current bullish: open=99, close=103 (engulfs prior)
        candles = _make_candles_with_pattern([
            Decimal("102"), Decimal("100"),  # Bearish
            Decimal("103"),  # Bullish engulfing
        ] + [Decimal("100")] * 20, timeframe=MarketTimeframe.M15)  # Pad with flat candles
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.M15: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error is None, f"Unexpected error: {result.error}"

    def test_bearish_engulfing_pattern(self):
        """Prior bullish followed by larger bearish candle that engulfs."""
        candles = _make_candles_with_pattern([
            Decimal("100"), Decimal("102"),  # Bullish
            Decimal("99"),  # Bearish engulfing
        ] + [Decimal("100")] * 20, timeframe=MarketTimeframe.M15)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.M15: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error is None

    def test_disabled_strategy(self):
        self.strategy.disable()
        candles = _make_candles_with_pattern([Decimal("100")] * 30, timeframe=MarketTimeframe.M15)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.M15: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error == "Strategy is disabled"

    def test_insufficient_candles(self):
        candles = _make_candles_with_pattern([Decimal("100"), Decimal("101")])
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert isinstance(result.signals, list)
        assert isinstance(result.rejections, list)

    def test_default_parameters(self):
        params = self.strategy.default_parameters
        assert params.get("min_body_ratio") == 0.5
        assert params.get("max_body_ratio") == 0.9

    def test_invalid_parameters(self):
        from src.indicators.base import IndicatorParameters
        params = IndicatorParameters(values={"min_body_ratio": 0.9, "max_body_ratio": 0.5})
        with pytest.raises(ValueError):
            self.strategy.validate_parameters(params)

    def test_signal_structure(self):
        candles = _make_candles_with_pattern([Decimal("100")] * 50)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        for sig in result.signals:
            assert sig.strategy_name == "PriceAction"
            assert sig.strategy_version == "1.0.0"
            assert sig.symbol == "EURUSD"
            assert sig.direction in ("LONG", "SHORT")
            assert sig.explanation is not None
