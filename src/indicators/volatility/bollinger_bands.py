"""Bollinger Bands (volatility indicator).

Formula:
    middle_t = SMA(close, period)                            (default period 20)
    std_t    = population standard deviation of close over period
    upper_t  = middle_t + (multiplier * std_t)               (default multiplier 2)
    lower_t  = middle_t - (multiplier * std_t)
    bandwidth_t = (upper_t - lower_t) / middle_t
    percent_b_t = (close_t - lower_t) / (upper_t - lower_t)

Standard deviation convention: population (divisor = period), which is the
classic Bollinger Bands convention.

Zero denominators:
    - middle == 0 → bandwidth = 0 (impossible for positive prices, guarded).
    - upper == lower → percent_b = 0.5 (price at the middle).

Default parameters: period=20, multiplier=2.
Outputs: ``upper``, ``middle``, ``lower``, ``bandwidth``, ``percent_b``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.indicators.base import (
    Indicator,
    IndicatorParameters,
    IndicatorResult,
    ReadinessStatus,
)
from src.indicators.calculator import sma, standard_deviation
from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)

_ZERO = Decimal(0)
_HALF = Decimal("0.5")


class BollingerBandsIndicator(Indicator):
    """Bollinger Bands with population standard deviation."""

    name = "Bollinger Bands"

    def __init__(self) -> None:
        self._default_period = 20
        self._default_multiplier = Decimal(2)

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(
            values={"period": self._default_period, "multiplier": self._default_multiplier}
        )

    @property
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        return {
            "period": {
                "type": "int",
                "default": 20,
                "min": 2,
                "max": 400,
                "description": "SMA / standard deviation lookback.",
            },
            "multiplier": {
                "type": "float",
                "default": 2.0,
                "min": 0.1,
                "max": 10.0,
                "description": "Standard-deviation multiplier for the bands.",
            },
        }

    @property
    def warmup_periods(self) -> int:
        return self._default_period - 1

    @property
    def output_names(self) -> List[str]:
        return ["upper", "middle", "lower", "bandwidth", "percent_b"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        period = parameters.get_int("period", self._default_period)
        multiplier = parameters.get_float("multiplier", float(self._default_multiplier))
        if period < 2:
            raise ValueError("Bollinger Bands period must be >= 2")
        if multiplier <= 0:
            raise ValueError("Bollinger Bands multiplier must be > 0")
        return IndicatorParameters(
            values={"period": period, "multiplier": Decimal(str(multiplier))}
        )

    def calculate(
        self,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
    ) -> IndicatorResult:
        if parameters is None:
            parameters = self.default_parameters
        parameters = self.validate_parameters(parameters)
        period = parameters.get_int("period", self._default_period)
        multiplier = parameters.get("multiplier", self._default_multiplier)

        n = len(candles)
        closes = [c.close for c in candles]

        middle = sma(closes, period)

        upper: List[Optional[Decimal]] = []
        lower: List[Optional[Decimal]] = []
        bandwidth: List[Optional[Decimal]] = []
        percent_b: List[Optional[Decimal]] = []

        for i in range(n):
            mid = middle[i]
            if mid is None:
                upper.append(None)
                lower.append(None)
                bandwidth.append(None)
                percent_b.append(None)
                continue

            std = standard_deviation(closes, period, i, sample=False)
            up = mid + multiplier * std
            lo = mid - multiplier * std
            upper.append(up)
            lower.append(lo)

            # Bandwidth = (upper - lower) / middle
            if mid == 0:
                bandwidth.append(_ZERO)
            else:
                bandwidth.append((up - lo) / mid)

            # Percent B = (close - lower) / (upper - lower)
            if up == lo:
                percent_b.append(_HALF)
            else:
                percent_b.append((closes[i] - lo) / (up - lo))

        first_valid = period - 1
        warmup = first_valid
        values: Dict[str, List[Optional[Decimal]]] = {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "bandwidth": bandwidth,
            "percent_b": percent_b,
        }
        if n <= warmup:
            readiness = ReadinessStatus.INSUFFICIENT
        else:
            readiness = ReadinessStatus.READY

        return IndicatorResult(
            symbol=candles[0].symbol if candles else "",
            instrument_type=InstrumentType.FOREX,
            timeframe=candles[0].timeframe if candles else MarketTimeframe.M1,
            indicator_name=self.name,
            parameters=parameters,
            calculation_timestamp=self._now(),
            source_candle_timestamp=candles[-1].timestamp if candles else self._now(),
            data_source=DataSource.SIMULATED,
            values=values,
            readiness=readiness,
            warmup_periods=warmup,
            metadata={
                "formula": "Bollinger Bands (population std dev)",
                "middle": "SMA(close, period)",
                "upper/lower": "middle +/- multiplier * std_dev",
                "bandwidth": "(upper - lower) / middle",
                "percent_b": "(close - lower) / (upper - lower)",
                "period": period,
                "multiplier": multiplier,
                "std_convention": "population (divisor = period)",
                "first_valid_index": first_valid,
            },
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
