"""Unit tests for SMA indicator."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.indicators import create_engine
from src.indicators.trend.sma import SMAIndicator
from src.market_data.models import DataSource, MarketTimeframe
from tests.indicators.conftest import make_candles, last_non_none

SYMBOL = "EURUSD"
TIMEFRAME = MarketTimeframe.M1


def _closes(values):
    return [Decimal(str(v)) for v in values]


@pytest.fixture
def engine():
    return create_engine()


def test_sma_default_periods_registered(engine):
    assert "SMA" in engine.supported_indicators()
    ind = engine.registry.get("SMA")
    assert ind is not None
    assert ind.name == "SMA"
    assert ind.warmup_periods == 199  # 200 - 1


def test_sma_known_values(engine):
    # closes: 10,11,12,13,14,15,16,17,18,19,20 ; SMA(5) -> [None x4, 12,13,...18]
    closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    candles = make_candles([(c, c, c, c, 100) for c in closes])
    result = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles)
    sma20 = result.values["sma_20"]
    # period 20 > 11 candles -> all None
    assert all(v is None for v in sma20)
    # Use period 5 via custom params
    from src.indicators.base import IndicatorParameters
    params = IndicatorParameters(values={"periods": [5]})
    result5 = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles, parameters=params)
    sma5 = result5.values["sma_5"]
    expected = [None, None, None, None, Decimal(12), Decimal(13), Decimal(14),
                Decimal(15), Decimal(16), Decimal(17), Decimal(18)]
    assert sma5 == expected, f"SMA(5) mismatch: {sma5}"


def test_sma_constant_price(engine):
    candles = make_candles([(Decimal("100"), Decimal("100"), Decimal("100"),
                             Decimal("100"), 100) for _ in range(30)])
    result = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles)
    assert last_non_none(result.values["sma_20"]) == Decimal("100")
    assert result.readiness.value == "ready"


def test_sma_insufficient_data(engine):
    candles = make_candles([(Decimal("10"), Decimal("10"), Decimal("10"),
                             Decimal("10"), 100) for _ in range(3)])
    result = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles)
    assert result.readiness.value in ("insufficient", "warming_up")
    assert all(v is None for v in result.values["sma_20"])


def test_sma_invalid_period(engine):
    from src.indicators.base import IndicatorParameters
    params = IndicatorParameters(values={"periods": [0]})
    ind = engine.registry.get("SMA")
    with pytest.raises(ValueError):
        ind.validate_parameters(params)


def test_sma_data_source_provenance(engine):
    candles = make_candles([(Decimal("10"), Decimal("10"), Decimal("10"),
                             Decimal("10"), 100) for _ in range(25)],
                           data_source=DataSource.HISTORICAL)
    result = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles,
                              data_source=DataSource.HISTORICAL)
    assert result.data_source == DataSource.HISTORICAL
    assert result.symbol == SYMBOL
    assert result.timeframe == TIMEFRAME
    assert result.indicator_name == "SMA"


def test_sma_output_metadata(engine):
    candles = make_candles([(Decimal("10"), Decimal("10"), Decimal("10"),
                             Decimal("10"), 100) for _ in range(25)])
    result = engine.calculate("SMA", SYMBOL, TIMEFRAME, candles)
    assert result.warmup_periods == 199
    assert "formula" in result.metadata
    assert result.parameters.get("periods") == [20, 50, 200]
