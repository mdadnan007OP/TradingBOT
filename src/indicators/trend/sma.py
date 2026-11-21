"""SMA — Simple Moving Average (trend indicator).

Formula:
    SMA_t(period) = (1 / period) * sum(close[t - period + 1 .. t])

Warm-up: ``period - 1`` candles produce ``None`` (insufficient data).
The first valid value appears at index ``period - 1``.

Default parameters: periods ``20``, ``50``, ``200``.
Supports calculating multiple period configurations in one call.
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
from src.indicators.calculator import sma
from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)


class SMAIndicator(Indicator):
    """Simple Moving Average."""

    name = "SMA"

    def __init__(self) -> None:
        self._default_periods = [20, 50, 200]

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={"periods": list(self._default_periods)})

    @property
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        return {
            "periods": {
                "type": "list[int]",
                "default": [20, 50, 200],
                "min": 1,
                "max": 1000,
                "description": "List of SMA periods to calculate.",
            }
        }

    @property
    def warmup_periods(self) -> int:
        return max(self._default_periods) - 1  # 199

    @property
    def output_names(self) -> List[str]:
        return [f"sma_{p}" for p in self._default_periods]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        periods = parameters.get("periods", self._default_periods)
        if isinstance(periods, (int, float)):
            periods = [int(periods)]
        periods = [int(p) for p in periods]
        if not periods:
            raise ValueError("SMA requires at least one period")
        if any(p < 1 for p in periods):
            raise ValueError("SMA periods must be >= 1")
        return IndicatorParameters(values={"periods": periods})

    def calculate(
        self,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
    ) -> IndicatorResult:
        if parameters is None:
            parameters = self.default_parameters
        parameters = self.validate_parameters(parameters)
        periods: List[int] = parameters.get("periods", self._default_periods)

        closes = [c.close for c in candles]
        values: Dict[str, List[Optional[Decimal]]] = {}
        full_warmup = 0
        readiness_warmup = 0
        for period in periods:
            series = sma(closes, period)
            values[f"sma_{period}"] = series
            full_warmup = max(full_warmup, period - 1)
            p_warmup = period - 1
            readiness_warmup = p_warmup if readiness_warmup == 0 else min(readiness_warmup, p_warmup)

        readiness = self._readiness(candles, readiness_warmup)
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
            warmup_periods=full_warmup,
            metadata={
                "formula": "SMA_t = mean(close[t-period+1 .. t])",
                "convention": "simple arithmetic mean",
                "periods": periods,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)

    @staticmethod
    def _readiness(candles: List[OHLCBar], warmup: int) -> ReadinessStatus:
        if not candles:
            return ReadinessStatus.INSUFFICIENT
        if len(candles) <= warmup:
            return ReadinessStatus.WARMING_UP
        return ReadinessStatus.READY
