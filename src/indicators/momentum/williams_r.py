"""Williams %R (momentum indicator).

Formula:
    %R_t = (HH_period - close_t) / (HH_period - LL_period) * -100

where HH/LL are the highest high / lowest low over ``period``.
Range is 0 (at the top of the range) to -100 (at the bottom).

Zero denominator: when HH == LL, %R = 0 (documented convention).

Default period: ``14``.
Outputs: ``williams_r``.
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
from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)

_ZERO = Decimal(0)
_NEG_HUNDRED = Decimal(-100)


class WilliamsRIndicator(Indicator):
    """Williams %R."""

    name = "Williams %R"

    def __init__(self) -> None:
        self._default_period = 14

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={"period": self._default_period})

    @property
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        return {
            "period": {
                "type": "int",
                "default": 14,
                "min": 1,
                "max": 200,
                "description": "Lookback for the high/low range.",
            }
        }

    @property
    def warmup_periods(self) -> int:
        return self._default_period - 1

    @property
    def output_names(self) -> List[str]:
        return ["williams_r"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        period = parameters.get_int("period", self._default_period)
        if period < 1:
            raise ValueError("Williams %R period must be >= 1")
        return IndicatorParameters(values={"period": period})

    def calculate(
        self,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
    ) -> IndicatorResult:
        if parameters is None:
            parameters = self.default_parameters
        parameters = self.validate_parameters(parameters)
        period = parameters.get_int("period", self._default_period)

        n = len(candles)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]

        williams_r: List[Optional[Decimal]] = []
        for i in range(n):
            if i < period - 1:
                williams_r.append(None)
                continue
            hh = max(highs[i - period + 1 : i + 1])
            ll = min(lows[i - period + 1 : i + 1])
            denom = hh - ll
            if denom == 0:
                williams_r.append(_ZERO)
            else:
                williams_r.append(_NEG_HUNDRED * (hh - closes[i]) / denom)

        first_valid = period - 1
        warmup = first_valid
        values: Dict[str, List[Optional[Decimal]]] = {"williams_r": williams_r}
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
                "formula": "%R = (HH - close) / (HH - LL) * -100",
                "period": period,
                "zero_denominator": "HH == LL → %R = 0",
                "first_valid_index": first_valid,
            },
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
