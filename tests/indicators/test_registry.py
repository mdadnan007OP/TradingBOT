"""Unit tests for the IndicatorRegistry."""

from __future__ import annotations

import pytest

from src.indicators import IndicatorRegistry, create_engine
from src.indicators.base import Indicator, IndicatorParameters
from src.indicators.trend.sma import SMAIndicator


@pytest.fixture
def registry():
    return IndicatorRegistry()


def test_registry_register_and_get(registry):
    ind = SMAIndicator()
    registry.register(ind)
    assert registry.exists("SMA")
    assert registry.get("SMA") is ind
    assert registry.indicator_count() == 1


def test_registry_duplicate_rejected(registry):
    registry.register(SMAIndicator())
    with pytest.raises(ValueError):
        registry.register(SMAIndicator())


def test_registry_unregister(registry):
    registry.register(SMAIndicator())
    assert registry.unregister("SMA") is True
    assert registry.exists("SMA") is False
    assert registry.unregister("SMA") is False


def test_registry_supported_indicators(registry):
    registry.register(SMAIndicator())
    from src.indicators.trend.ema import EMAIndicator
    registry.register(EMAIndicator())
    names = registry.supported_indicators()
    assert "EMA" in names and "SMA" in names
    assert names == sorted(names)


def test_registry_parameter_schema(registry):
    registry.register(SMAIndicator())
    schema = registry.parameter_schema("SMA")
    assert schema is not None
    assert "periods" in schema
    assert registry.parameter_schema("Nonexistent") is None


def test_registry_validate_parameters(registry):
    registry.register(SMAIndicator())
    params = registry.validate_parameters("SMA", IndicatorParameters(values={"periods": [10]}))
    assert params.get("periods") == [10]
    with pytest.raises(ValueError):
        registry.validate_parameters("Nonexistent", IndicatorParameters())
    with pytest.raises(ValueError):
        registry.validate_parameters("SMA", IndicatorParameters(values={"periods": [0]}))


def test_registry_rejects_non_indicator(registry):
    with pytest.raises(TypeError):
        registry.register("not an indicator")  # type: ignore[arg-type]


def test_create_engine_has_all_builtins():
    eng = create_engine()
    assert eng.registry.indicator_count() >= 13
    expected = ["SMA", "EMA", "ADX", "Ichimoku", "RSI", "MACD", "Stochastic",
                "CCI", "Williams %R", "ATR", "Bollinger Bands", "VWAP",
                "Classic Pivot Points"]
    for name in expected:
        assert eng.indicator_exists(name), f"Missing built-in: {name}"
