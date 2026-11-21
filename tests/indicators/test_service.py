"""Unit tests for the IndicatorEngine service."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.indicators.base import IndicatorParameters, ReadinessStatus
from src.market_data.models import DataSource, MarketTimeframe
from tests.indicators.conftest import make_candles

SYMBOL = "EURUSD"
TIMEFRAME = MarketTimeframe.M1


@pytest.fixture
def engine():
    return create_engine()


def test_service_calculate_rich_result(engine):
    candles = make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                             Decimal("100"), 100) for _ in range(25)])
    result = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles,
                              data_source=DataSource.HISTORICAL)
    assert result.symbol == SYMBOL
    assert result.timeframe == TIMEFRAME
    assert result.indicator_name == "SMA"
    assert result.data_source == DataSource.HISTORICAL
    assert result.readiness == ReadinessStatus.READY
    assert result.bar_count == 25
    assert result.last_value("sma_20") == Decimal(100)


def test_service_unknown_indicator(engine):
    candles = make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                             Decimal("100"), 100) for _ in range(5)])
    with pytest.raises(ValueError):
        engine.calculate("NonexistentIndicator", SYMBOL, TIMEFRAME, candles)


def test_service_invalid_candles(engine):
    with pytest.raises(ValueError):
        engine.calculate("SMA", SYMBOL, TIMEFRAME, [])


def test_service_unknown_symbol_rejected(engine):
    candles = make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                             Decimal("100"), 100) for _ in range(5)],
                           symbol="OTHER")
    with pytest.raises(ValueError):
        engine.calculate("SMA", SYMBOL, TIMEFRAME, candles)


def test_service_compute_compatibility(engine):
    closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    candles = make_candles([(c, c, c, c, 100) for c in closes])
    output = engine.compute("SMA", SYMBOL, candles, periods=[5])
    assert "sma_5" in output
    series = output["sma_5"]
    assert series[4] == 12.0  # SMA(5) at index 4
    # None values map to nan
    import math
    assert math.isnan(series[0])


def test_service_register_custom_indicator(engine):
    from src.indicators.base import Indicator

    class CustomIndicator(Indicator):
        name = "CUSTOM"

        @property
        def default_parameters(self):
            return IndicatorParameters()

        @property
        def parameter_schema(self):
            return {}

        @property
        def warmup_periods(self):
            return 0

        @property
        def output_names(self):
            return ["custom_val"]

        def validate_parameters(self, parameters):
            return parameters

        def calculate(self, candles, parameters=None):
            from src.indicators.base import IndicatorResult, ReadinessStatus
            from src.market_data.models import DataSource, InstrumentType, MarketTimeframe
            from datetime import datetime, timezone
            vals = [Decimal(c.close) for c in candles]
            return IndicatorResult(
                symbol=candles[0].symbol, instrument_type=InstrumentType.FOREX,
                timeframe=candles[0].timeframe, indicator_name="CUSTOM",
                parameters=parameters or IndicatorParameters(),
                calculation_timestamp=datetime.now(timezone.utc),
                source_candle_timestamp=candles[-1].timestamp,
                data_source=DataSource.SIMULATED,
                values={"custom_val": vals},
                readiness=ReadinessStatus.READY,
                warmup_periods=0,
            )

    engine.register_indicator(CustomIndicator())
    assert engine.indicator_exists("CUSTOM")
    candles = make_candles([(Decimal("10"), Decimal("10"), Decimal("10"),
                             Decimal("10"), 100) for _ in range(3)])
    result = engine.calculate("CUSTOM", SYMBOL, TIMEFRAME, candles)
    assert result.values["custom_val"] == [Decimal(10), Decimal(10), Decimal(10)]
