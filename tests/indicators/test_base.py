"""Unit tests for indicator base models."""

from __future__ import annotations

from datetime import datetime

from decimal import Decimal

import pytest

from src.indicators.base import (
    IndicatorParameters,
    IndicatorResult,
    ReadinessStatus,
)
from src.market_data.models import DataSource, InstrumentType, MarketTimeframe


def test_readiness_status_values():
    assert ReadinessStatus.READY == "ready"
    assert ReadinessStatus.WARMING_UP == "warming_up"
    assert ReadinessStatus.INSUFFICIENT == "insufficient"
    assert ReadinessStatus.INVALID == "invalid"


def test_indicator_parameters_typed_accessors():
    p = IndicatorParameters(values={"period": 14, "mult": "2.5", "flag": True})
    assert p.get("period") == 14
    assert p.get_int("period", 0) == 14
    assert p.get_float("mult", 1.0) == 2.5
    assert p.get_bool("flag", False) is True
    assert p.get_bool("missing", False) is False
    assert p.get_int("missing", 7) == 7
    assert p.get_float("missing", 2.5) == 2.5


def test_indicator_result_alignment_and_last_value():
    values = {"sma": [None, None, Decimal(10), Decimal(11)]}
    result = IndicatorResult(
        symbol="EURUSD", instrument_type=InstrumentType.FOREX,
        timeframe=MarketTimeframe.M1, indicator_name="SMA",
        parameters=IndicatorParameters(),
        calculation_timestamp=datetime.now(),
        source_candle_timestamp=datetime.now(),
        data_source=DataSource.SIMULATED, values=values,
        readiness=ReadinessStatus.READY, warmup_periods=2,
    )
    assert result.bar_count == 4
    assert result.output_names == ["sma"]
    assert result.last_value("sma") == Decimal(11)
    assert result.last_value("missing") is None
