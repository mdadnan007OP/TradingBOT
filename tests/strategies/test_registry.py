"""Tests for the Strategy Registry."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators.base import IndicatorParameters
from src.market_data.models import MarketTimeframe
from src.strategies.base import MarketRegime, SignalDirection, Strategy
from src.strategies.registry import StrategyRegistry


class _DummyStrategy(Strategy):
    """Minimal strategy for registry testing."""

    name = "DummyStrategy"
    version = "1.0.0"
    _enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    @property
    def required_timeframes(self):
        return [MarketTimeframe.H1]

    @property
    def supported_instruments(self):
        return ["EURUSD", "GBPUSD"]

    @property
    def supported_regimes(self):
        return [MarketRegime.TRENDING, MarketRegime.RANGING]

    @property
    def default_parameters(self):
        return IndicatorParameters(values={"ema_period": 14})

    def validate_parameters(self, parameters):
        return parameters

    def analyze(self, symbol, candles_by_timeframe, indicator_engine,
                parameters=None, data_source="simulated"):
        from src.strategies.base import SignalRejection, StrategyResult
        return StrategyResult(
            strategy_name=self.name,
            symbol=symbol,
            timeframe=MarketTimeframe.H1,
            signals=[],
            rejections=[],
            market_regime=MarketRegime.UNKNOWN,
            indicator_snapshots={},
        )


class TestStrategyRegistry:
    def test_register_and_get(self):
        registry = StrategyRegistry()
        strat = _DummyStrategy()
        assert registry.register(strat) is True
        assert registry.exists("DummyStrategy") is True
        assert registry.get("DummyStrategy") is strat
        assert registry.strategy_count() == 1

    def test_register_duplicate_rejected(self):
        registry = StrategyRegistry()
        strat = _DummyStrategy()
        assert registry.register(strat) is True
        assert registry.register(_DummyStrategy()) is False  # duplicate name

    def test_unregister(self):
        registry = StrategyRegistry()
        strat = _DummyStrategy()
        registry.register(strat)
        assert registry.unregister("DummyStrategy") is True
        assert registry.exists("DummyStrategy") is False
        assert registry.unregister("DummyStrategy") is False  # already gone

    def test_supported_strategies(self):
        registry = StrategyRegistry()
        registry.register(_DummyStrategy())
        names = registry.supported_strategies()
        assert "DummyStrategy" in names

    def test_enable_disable(self):
        registry = StrategyRegistry()
        strat = _DummyStrategy()
        registry.register(strat)
        assert registry.is_enabled("DummyStrategy") is True

        assert registry.disable("DummyStrategy") is True
        assert registry.is_enabled("DummyStrategy") is False
        assert "DummyStrategy" in registry.disabled_strategies()

        assert registry.enable("DummyStrategy") is True
        assert registry.is_enabled("DummyStrategy") is True
        assert "DummyStrategy" in registry.enabled_strategies()

    def test_enable_nonexistent(self):
        registry = StrategyRegistry()
        assert registry.enable("Nope") is False

    def test_disable_nonexistent(self):
        registry = StrategyRegistry()
        assert registry.disable("Nope") is False

    def test_set_get_parameters(self):
        registry = StrategyRegistry()
        strat = _DummyStrategy()
        registry.register(strat)
        assert registry.set_parameters("DummyStrategy", {"ema_period": 21}) is True
        params = registry.get_parameters("DummyStrategy")
        assert params["ema_period"] == 21

    def test_set_parameters_nonexistent(self):
        registry = StrategyRegistry()
        assert registry.set_parameters("Nope", {}) is False

    def test_strategy_info(self):
        registry = StrategyRegistry()
        strat = _DummyStrategy()
        registry.register(strat)
        info = registry.strategy_info("DummyStrategy")
        assert info is not None
        assert info["name"] == "DummyStrategy"
        assert info["version"] == "1.0.0"
        assert info["enabled"] is True
        assert "H1" in info["required_timeframes"]
        assert info["supported_instruments"] == ["EURUSD", "GBPUSD"]

    def test_strategy_info_nonexistent(self):
        registry = StrategyRegistry()
        assert registry.strategy_info("Nope") is None
