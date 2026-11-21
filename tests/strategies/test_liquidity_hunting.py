"""Tests for the Liquidity Hunting Strategy."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.market_data.models import DataSource, MarketTimeframe
from src.strategies.liquidity import LiquidityHuntingStrategy


class TestLiquidityHuntingStrategy:
    def setup_method(self):
        self.strategy = LiquidityHuntingStrategy()
        self.engine = create_engine()

    def test_strategy_properties(self):
        assert self.strategy.name == "LiquidityHunting"
        assert self.strategy.version == "1.0.0"
        assert self.strategy.enabled is True

    def test_enable_disable(self):
        self.strategy.disable()
        assert self.strategy.enabled is False
        self.strategy.enable()
        assert self.strategy.enabled is True

    def test_insufficient_candles(self):
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100")] * 5)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert isinstance(result.signals, list)
        assert isinstance(result.rejections, list)

    def test_disabled_strategy(self):
        self.strategy.disable()
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100")] * 50, timeframe=MarketTimeframe.M15)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.M15: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error == "Strategy is disabled"

    def test_liquidity_proxy_marker(self):
        """Verify that signals are marked as liquidity proxy only."""
        # Create candles with a sweep pattern
        closes = []
        # Build up to a swing low, then sweep below, then close back inside
        for i in range(60):
            if i < 30:
                closes.append(Decimal("100") - Decimal(str(i * 0.1)))  # Down to swing low
            elif i == 30:
                closes.append(Decimal("97"))  # Below swing low (sweep)
            else:
                closes.append(Decimal("98"))  # Close back inside
        from tests.strategies.conftest import make_candles
        candles = make_candles(closes, timeframe=MarketTimeframe.M15)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.M15: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error is None
        for sig in result.signals:
            assert sig.metadata.get("liquidity_proxy_only") is True

    def test_default_parameters(self):
        params = self.strategy.default_parameters
        assert params.get("price_tolerance") == 0.001
        assert params.get("min_swing_strength") == 3

    def test_invalid_parameters(self):
        from src.indicators.base import IndicatorParameters
        params = IndicatorParameters(values={"price_tolerance": 0})
        with pytest.raises(ValueError):
            self.strategy.validate_parameters(params)

    def test_signal_structure(self):
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100")] * 50)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        for sig in result.signals:
            assert sig.strategy_name == "LiquidityHunting"
            assert sig.direction in ("LONG", "SHORT")
