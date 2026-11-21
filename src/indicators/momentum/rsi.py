"""RSI — Relative Strength Index (momentum indicator, Wilder's method).

Formula:
    delta_t   = close_t - close_{t-1}
    gain_t    = max(delta_t, 0)
    loss_t    = max(-delta_t, 0)
    avg_gain  = Wilder-smoothed gain over ``period``
    avg_loss  = Wilder-smoothed loss over ``period``
    RS        = avg_gain / avg_loss
    RSI_t     = 100 - (100 / (1 + RS))

Zero denominator: if avg_loss == 0, RSI = 100 (all gains).
First valid value at index ``period`` (need ``period`` price changes).

Default period: ``14``.
Outputs: ``rsi``.
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
from src.indicators.calculator import wilder_smooth
from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)


class RSIIndicator(Indicator):
    """Wilder's Relative Strength Index."""

    name = "RSI"

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
                "min": 2,
                "max": 100,
                "description": "Wilder smoothing period for RSI.",
            }
        }

    @property
    def warmup_periods(self) -> int:
        return self._default_period

    @property
    def output_names(self) -> List[str]:
        return ["rsi"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        period = parameters.get_int("period", self._default_period)
        if period < 2:
            raise ValueError("RSI period must be >= 2")
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
        closes = [c.close for c in candles]

        # Gains and losses per bar (bar 0 has no change).
        gains: List[Decimal] = [_ZERO] * n
        losses: List[Decimal] = [_ZERO] * n
        for i in range(1, n):
            delta = closes[i] - closes[i - 1]
            if delta > 0:
                gains[i] = delta
            elif delta < 0:
                losses[i] = -delta
            # delta == 0 → both remain 0.

        avg_gain = wilder_smooth(gains, period)
        avg_loss = wilder_smooth(losses, period)

        rsi: List[Optional[Decimal]] = []
        for i in range(n):
            ag = avg_gain[i]
            al = avg_loss[i]
            if ag is None or al is None:
                rsi.append(None)
            elif i < period:
                # First valid RSI at index `period` (need `period` price changes).
                rsi.append(None)
            elif al == _ZERO:
                if ag == _ZERO:
                    # No movement at all (flat) → neutral.
                    rsi.append(Decimal(50))
                else:
                    # All gains, no losses → RSI = 100.
                    rsi.append(_HUNDRED)
            else:
                rs = ag / al
                rsi.append(_HUNDRED - (_HUNDRED / (Decimal(1) + rs)))

        first_valid = period
        warmup = first_valid
        values: Dict[str, List[Optional[Decimal]]] = {"rsi": rsi}
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
                "formula": "RSI = 100 - 100/(1+RS), RS = avg_gain/avg_loss",
                "smoothing": "Wilder",
                "period": period,
                "zero_denominator": "avg_loss == 0 and avg_gain == 0 → RSI = 50 (neutral); avg_loss == 0 and avg_gain > 0 → RSI = 100",
                "first_valid_index": first_valid,
            },
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
