"""MACD — Moving Average Convergence Divergence (momentum indicator).

Formula:
    fast_ema  = EMA(close, fast_period)      (default 12)
    slow_ema  = EMA(close, slow_period)      (default 26)
    macd_line = fast_ema - slow_ema
    signal    = EMA(macd_line, signal_period) (default 9)
    histogram = macd_line - signal

EMA uses SMA initialization (see calculator.ema).
First valid MACD at index ``slow_period - 1``.
First valid signal/histogram at index ``slow_period + signal_period - 2``.

Default parameters: 12, 26, 9.
Outputs: ``macd``, ``signal``, ``histogram``.
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
from src.indicators.calculator import ema
from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)

_ZERO = Decimal(0)


class MACDIndicator(Indicator):
    """Moving Average Convergence Divergence."""

    name = "MACD"

    def __init__(self) -> None:
        self._default_fast = 12
        self._default_slow = 26
        self._default_signal = 9

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(
            values={
                "fast_period": self._default_fast,
                "slow_period": self._default_slow,
                "signal_period": self._default_signal,
            }
        )

    @property
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        return {
            "fast_period": {
                "type": "int",
                "default": 12,
                "min": 1,
                "max": 200,
                "description": "Fast EMA period.",
            },
            "slow_period": {
                "type": "int",
                "default": 26,
                "min": 1,
                "max": 400,
                "description": "Slow EMA period.",
            },
            "signal_period": {
                "type": "int",
                "default": 9,
                "min": 1,
                "max": 200,
                "description": "Signal EMA period applied to the MACD line.",
            },
        }

    @property
    def warmup_periods(self) -> int:
        return self._default_slow + self._default_signal - 2

    @property
    def output_names(self) -> List[str]:
        return ["macd", "signal", "histogram"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        fast = parameters.get_int("fast_period", self._default_fast)
        slow = parameters.get_int("slow_period", self._default_slow)
        signal = parameters.get_int("signal_period", self._default_signal)
        if fast < 1 or slow < 1 or signal < 1:
            raise ValueError("MACD periods must be >= 1")
        if fast >= slow:
            raise ValueError("MACD fast_period must be < slow_period")
        return IndicatorParameters(
            values={
                "fast_period": fast,
                "slow_period": slow,
                "signal_period": signal,
            }
        )

    def calculate(
        self,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
    ) -> IndicatorResult:
        if parameters is None:
            parameters = self.default_parameters
        parameters = self.validate_parameters(parameters)
        fast = parameters.get_int("fast_period", self._default_fast)
        slow = parameters.get_int("slow_period", self._default_slow)
        signal_p = parameters.get_int("signal_period", self._default_signal)

        n = len(candles)
        closes = [c.close for c in candles]

        fast_ema = ema(closes, fast)
        slow_ema = ema(closes, slow)

        # MACD line (None where either EMA is None).
        macd_line: List[Optional[Decimal]] = []
        for i in range(n):
            f = fast_ema[i]
            s = slow_ema[i]
            macd_line.append(None if (f is None or s is None) else f - s)

        # Signal line = EMA of MACD line over valid MACD values only.
        # MACD is None for a contiguous warm-up prefix; zero-filling would
        # contaminate the EMA seed, so we start the signal EMA at the first
        # valid MACD value and leave earlier positions as None.
        first_macd = next((i for i in range(n) if macd_line[i] is not None), None)

        signal: List[Optional[Decimal]] = []
        histogram: List[Optional[Decimal]] = []

        if first_macd is None:
            signal = [None] * n
            histogram = [None] * n
        else:
            first_signal = first_macd + signal_p - 1
            if first_signal >= n:
                signal = [None] * n
                histogram = [None] * n
            else:
                # Seed: SMA of the first signal_p valid MACD values.
                seed_vals = [macd_line[i] for i in range(first_macd, first_signal + 1)]
                signal_val = sum(seed_vals) / Decimal(signal_p)
                k = Decimal(2) / Decimal(signal_p + 1)
                one_minus_k = Decimal(1) - k

                for i in range(n):
                    if i < first_signal:
                        signal.append(None)
                    else:
                        m = macd_line[i]
                        if m is None:
                            signal.append(None)
                        else:
                            signal_val = m * k + signal_val * one_minus_k
                            signal.append(signal_val)

                for i in range(n):
                    m = macd_line[i]
                    s = signal[i]
                    if m is None or s is None:
                        histogram.append(None)
                    else:
                        histogram.append(m - s)

        first_valid = slow + signal_p - 2
        warmup = first_valid
        values: Dict[str, List[Optional[Decimal]]] = {
            "macd": macd_line,
            "signal": signal,
            "histogram": histogram,
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
                "formula": "MACD = EMA_fast - EMA_slow; Signal = EMA(MACD, signal); Hist = MACD - Signal",
                "ema_initialization": "SMA seed",
                "fast_period": fast,
                "slow_period": slow,
                "signal_period": signal_p,
                "first_valid_index": first_valid,
            },
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
