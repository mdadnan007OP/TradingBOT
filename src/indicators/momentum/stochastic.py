"""Stochastic Oscillator (momentum indicator).

Formula:
    raw_k_t = (close_t - LL_k) / (HH_k - LL_k) * 100
              where HH_k/LL_k = highest high / lowest low over ``k_period``
    k_t     = SMA(raw_k, k_smoothing)          # slow %K
    d_t     = SMA(k, d_period)                 # %D signal

Zero denominator: when HH_k == LL_k, raw_k = 0 (documented convention).
This is the "slow" stochastic: %K is smoothed before the %D signal.

Default parameters: k_period=14, k_smoothing=3, d_period=3.
Outputs: ``k`` (slow %K), ``d`` (%D signal).
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

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)


class StochasticIndicator(Indicator):
    """Slow Stochastic Oscillator."""

    name = "Stochastic"

    def __init__(self) -> None:
        self._default_k_period = 14
        self._default_k_smooth = 3
        self._default_d_period = 3

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(
            values={
                "k_period": self._default_k_period,
                "k_smoothing": self._default_k_smooth,
                "d_period": self._default_d_period,
            }
        )

    @property
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        return {
            "k_period": {
                "type": "int",
                "default": 14,
                "min": 1,
                "max": 200,
                "description": "Lookback for %K range.",
            },
            "k_smoothing": {
                "type": "int",
                "default": 3,
                "min": 1,
                "max": 50,
                "description": "Smoothing applied to raw %K (slow %K).",
            },
            "d_period": {
                "type": "int",
                "default": 3,
                "min": 1,
                "max": 50,
                "description": "Smoothing applied to slow %K (%D signal).",
            },
        }

    @property
    def warmup_periods(self) -> int:
        return (
            self._default_k_period
            + self._default_k_smooth
            + self._default_d_period
            - 3
        )

    @property
    def output_names(self) -> List[str]:
        return ["k", "d"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        kp = parameters.get_int("k_period", self._default_k_period)
        ks = parameters.get_int("k_smoothing", self._default_k_smooth)
        dp = parameters.get_int("d_period", self._default_d_period)
        if kp < 1 or ks < 1 or dp < 1:
            raise ValueError("Stochastic periods must be >= 1")
        return IndicatorParameters(
            values={"k_period": kp, "k_smoothing": ks, "d_period": dp}
        )

    def calculate(
        self,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
    ) -> IndicatorResult:
        if parameters is None:
            parameters = self.default_parameters
        parameters = self.validate_parameters(parameters)
        kp = parameters.get_int("k_period", self._default_k_period)
        ks = parameters.get_int("k_smoothing", self._default_k_smooth)
        dp = parameters.get_int("d_period", self._default_d_period)

        n = len(candles)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]

        # Raw %K over k_period window.
        raw_k: List[Optional[Decimal]] = []
        for i in range(n):
            if i < kp - 1:
                raw_k.append(None)
                continue
            hh = max(highs[i - kp + 1 : i + 1])
            ll = min(lows[i - kp + 1 : i + 1])
            denom = hh - ll
            if denom == 0:
                raw_k.append(_ZERO)
            else:
                raw_k.append(_HUNDRED * (closes[i] - ll) / denom)

        # Slow %K = SMA(raw_k, k_smoothing).
        slow_k = sma(raw_k, ks)

        # %D = SMA(slow_k, d_period).
        d_series = sma(slow_k, dp)

        first_valid = kp + ks + dp - 3
        warmup = first_valid
        values: Dict[str, List[Optional[Decimal]]] = {"k": slow_k, "d": d_series}
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
                "formula": "raw_K = (close - LL)/(HH - LL)*100; slow_K = SMA(raw_K, k_smoothing); D = SMA(slow_K, d_period)",
                "k_period": kp,
                "k_smoothing": ks,
                "d_period": dp,
                "zero_denominator": "HH == LL → raw_k = 0",
                "first_valid_index": first_valid,
            },
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
