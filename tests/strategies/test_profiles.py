"""Tests for Scalping, Intraday, and Swing Profiles."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.market_data.models import DataSource, MarketTimeframe
from src.strategies.scalping import ScalpingProfile
from src.strategies.intraday import IntradayProfile
from src.strategies.swing import SwingProfile


class TestScalpingProfile:
    def setup_method(self):
        self.strategy = ScalpingProfile()
        self.engine = create_engine()

    def test_strategy_properties(self):
        assert self.strategy.name == "ScalpingProfile"
        assert self.strategy.version == "1.0.0"

    def test_enable_disable(self):
        self.strategy.disable()
        assert self.strategy.enabled is False
        self.strategy.enable()
        assert self.strategy.enabled is True

    def test_default_parameters(self):
        params = self.strategy.default_parameters
        assert params.get("ema_fast") == 9
        assert params.get("ema_slow") == 21

    def test_invalid_parameters(self):
        from src.indicators.base import IndicatorParameters
        params = IndicatorParameters(values={"ema_fast": 21, "ema_slow": 9})
        with pytest.raises(ValueError):
            self.strategy.validate_parameters(params)

    def test_analysis(self):
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100")] * 50)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.M5: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error is None
        assert isinstance(result.signals, list)

    def test_disabled(self):
        self.strategy.disable()
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100")] * 50)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.M5: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error == "Strategy is disabled"


class TestIntradayProfile:
    def setup_method(self):
        self.strategy = IntradayProfile()
        self.engine = create_engine()

    def test_strategy_properties(self):
        assert self.strategy.name == "IntradayProfile"
        assert self.strategy.version == "1.0.0"

    def test_default_parameters(self):
        params = self.strategy.default_parameters
        assert params.get("ema_period") == 50
        assert params.get("adx_period") == 14

    def test_analysis(self):
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100")] * 50)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H1: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error is None
        assert isinstance(result.signals, list)

    def test_disabled(self):
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


class TestSwingProfile:
    def setup_method(self):
        self.strategy = SwingProfile()
        self.engine = create_engine()

    def test_strategy_properties(self):
        assert self.strategy.name == "SwingProfile"
        assert self.strategy.version == "1.0.0"

    def test_default_parameters(self):
        params = self.strategy.default_parameters
        assert params.get("ema_period") == 50
        assert params.get("sma_period") == 200

    def test_analysis(self):
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100")] * 60)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H4: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error is None
        assert isinstance(result.signals, list)

    def test_disabled(self):
        self.strategy.disable()
        from tests.strategies.conftest import make_candles
        candles = make_candles([Decimal("100")] * 60)
        result = self.strategy.analyze(
            "EURUSD",
            {MarketTimeframe.H4: candles},
            self.engine,
            data_source=DataSource.SIMULATED,
        )
        assert result.error == "Strategy is disabled"
