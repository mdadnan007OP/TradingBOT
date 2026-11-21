"""ATR — Average True Range (volatility indicator, Wilder's smoothing).

Formula:
    TR_t  = max(High - Low, |High - PrevClose|, |Low - PrevClose|)
          TR_0 = High_0 - Low_0  (no previous close)
    ATR_{period-1} = SMA(TR[0 .. period-1])       # Wilder initialization
    ATR_t = (ATR_{t-1} * (period - 1) + TR_t) / period   # Wilder recursive

Default period: ``14``.
Outputs: ``atr``.
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
from src.indicators.calculator import true_range
from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)

_ZERO = Decimal(0)


class ATRIndicator(Indicator):
    """Average True Range using Wilder's smoothing."""

    name = "ATR"

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
                "description": "Wilder smoothing period for ATR.",
            }
        }

    @property
    def warmup_periods(self) -> int:
        return self._default_period - 1

    @property
    def output_names(self) -> List[str]:
        return ["atr"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        period = parameters.get_int("period", self._default_period)
        if period < 1:
            raise ValueError("ATR period must be >= 1")
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

        # True Range per bar.
        trs: List[Decimal] = []
        for i in range(n):
            if i == 0:
                trs.append(highs[0] - lows[0])
            else:
                trs.append(true_range(highs[i], lows[i], closes[i - 1]))

        # Wilder's ATR: SMA seed then recursive smoothing.
        atr: List[Optional[Decimal]] = []
        prev_atr: Optional[Decimal] = None
        for i in range(n):
            tr = trs[i]
            if i < period - 1:
                atr.append(None)
                continue
            if i == period - 1:
                window = trs[:period]
                prev_atr = sum(window) / Decimal(period)
                atr.append(prev_atr)
            else:
                if prev_atr is None:
                    atr.append(None)
                else:
                    current = (prev_atr * Decimal(period - 1) + tr) / Decimal(period)
                    prev_atr = current
                    atr.append(current)

        first_valid = period - 1
        warmup = first_valid
        values: Dict[str, List[Optional[Decimal]]] = {"atr": atr}
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
                "formula": "ATR = Wilder-smoothed True Range",
                "tr": "max(High-Low, |High-PrevClose|, |Low-PrevClose|)",
                "smoothing": "Wilder",
                "period": period,
                "first_valid_index": first_valid,
            },
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
