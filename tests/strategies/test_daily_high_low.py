"""Tests for the Daily High/Low Strategy."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.market_data.models import DataSource, MarketTimeframe
from src.strategies.daily_levels import DailyHighLowStrategy


class TestDailyHighLowStrategy:
    def setup_method(self):
        self.strategy = DailyHighLowStrategy()
        self.engine = create_engine()

    def test_strategy_properties(self):
        assert self.strategy.name == "DailyHighLow"
        assert self.strategy.version == "1.0.0"
        assert self.strategy.enabled is True

    def test_enable_disable(self):
        self.strategy.disable()
        assert self.strategy.enabled is False
        self.strategy.enable()
        assert self.strategy.enabled is True

    def test_insufficient_candles(self):
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100")] * 2)
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
        candles = make_candles([Decimal("100")] * 50)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error == "Strategy is disabled"

    def test_default_parameters(self):
        params = self.strategy.default_parameters
        assert params.get("use_previous_day") is True
        assert params.get("use_previous_week") is True

    def test_invalid_parameters(self):
        from src.indicators.base import IndicatorParameters
        params = IndicatorParameters(values={"breakout_confirmation_candles": 0})
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
        assert result.error is None
        for sig in result.signals:
            assert sig.strategy_name == "DailyHighLow"
            assert sig.direction in ("LONG", "SHORT")
