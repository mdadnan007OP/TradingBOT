"""CCI — Commodity Channel Index (momentum indicator).

Formula:
    TP_t      = (High + Low + Close) / 3                     # typical price
    SMA_TP    = SMA(TP, period)
    mean_dev  = mean(|TP - SMA_TP|) over the period window
    CCI_t     = (TP_t - SMA_TP_t) / (0.015 * mean_dev_t)

The constant 0.015 means roughly 70% of CCI values fall between -100 and +100.

Zero denominator: when mean deviation == 0, CCI = 0 (documented).

Default period: ``20``.
Outputs: ``cci``.
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
from src.indicators.calculator import mean_deviation, sma, typical_price
from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)

_ZERO = Decimal(0)
_CCI_CONST = Decimal("0.015")


class CCIIndicator(Indicator):
    """Commodity Channel Index."""

    name = "CCI"

    def __init__(self) -> None:
        self._default_period = 20

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={"period": self._default_period})

    @property
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        return {
            "period": {
                "type": "int",
                "default": 20,
                "min": 2,
                "max": 200,
                "description": "CCI lookback period.",
            },
            "constant": {
                "type": "float",
                "default": 0.015,
                "min": 0.001,
                "max": 1.0,
                "description": "CCI scaling constant (0.015 standard).",
            },
        }

    @property
    def warmup_periods(self) -> int:
        return self._default_period - 1

    @property
    def output_names(self) -> List[str]:
        return ["cci"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        period = parameters.get_int("period", self._default_period)
        constant = parameters.get_float("constant", 0.015)
        if period < 2:
            raise ValueError("CCI period must be >= 2")
        if constant <= 0:
            raise ValueError("CCI constant must be > 0")
        return IndicatorParameters(values={"period": period, "constant": constant})

    def calculate(
        self,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
    ) -> IndicatorResult:
        if parameters is None:
            parameters = self.default_parameters
        parameters = self.validate_parameters(parameters)
        period = parameters.get_int("period", self._default_period)
        constant = Decimal(str(parameters.get_float("constant", 0.015)))

        n = len(candles)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]

        typical = [typical_price(highs[i], lows[i], closes[i]) for i in range(n)]
        sma_tp = sma(typical, period)

        cci: List[Optional[Decimal]] = []
        for i in range(n):
            tp = typical[i]
            sma_v = sma_tp[i]
            if sma_v is None:
                cci.append(None)
                continue
            md = mean_deviation(typical, period, i) if i >= period - 1 else _ZERO
            denom = constant * md
            if denom == 0:
                cci.append(_ZERO)
            else:
                cci.append((tp - sma_v) / denom)

        first_valid = period - 1
        warmup = first_valid
        values: Dict[str, List[Optional[Decimal]]] = {"cci": cci}
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
                "formula": "CCI = (TP - SMA_TP) / (0.015 * mean_deviation)",
                "tp": "(High + Low + Close) / 3",
                "period": period,
                "constant": constant,
                "zero_denominator": "mean_deviation == 0 → CCI = 0",
                "first_valid_index": first_valid,
            },
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
