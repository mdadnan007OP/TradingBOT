"""Ichimoku Cloud (trend indicator).

Causal (look-ahead safe) calculation. All lines use past data only; the
leading spans (Span A / Span B) are reported at their calculation index and are
**not** forward-displaced, which prevents historical look-ahead leakage.

Components:
    Conversion Line (Tenkan-sen)  = (HH + LL) / 2 over ``conversion_period``  (default 9)
    Base Line (Kijun-sen)         = (HH + LL) / 2 over ``base_period``        (default 26)
    Leading Span A (Senkou A)     = (Conversion + Base) / 2                   (causal, not displaced)
    Leading Span B (Senkou B)     = (HH + LL) / 2 over ``span_b_period``      (default 52, causal)
    Lagging Span (Chikou Span)    = Close delayed by ``base_period``          (default 26, causal)

Warm-up: ``span_b_period - 1`` (default 51) before Span B is valid.
Default parameters: 9, 26, 52.

Outputs: ``conversion_line``, ``base_line``, ``span_a``, ``span_b``, ``lagging_span``.
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
_TWO = Decimal(2)


def _highest_high(highs: List[Decimal], start: int, end: int) -> Decimal:
    return max(highs[start : end + 1])


def _lowest_low(lows: List[Decimal], start: int, end: int) -> Decimal:
    return min(lows[start : end + 1])


class IchimokuIndicator(Indicator):
    """Ichimoku Cloud, causally calculated."""

    name = "Ichimoku"

    def __init__(self) -> None:
        self._default_conversion = 9
        self._default_base = 26
        self._default_span_b = 52

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(
            values={
                "conversion_period": self._default_conversion,
                "base_period": self._default_base,
                "span_b_period": self._default_span_b,
            }
        )

    @property
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        return {
            "conversion_period": {
                "type": "int",
                "default": 9,
                "min": 2,
                "max": 200,
                "description": "Tenkan-sen period.",
            },
            "base_period": {
                "type": "int",
                "default": 26,
                "min": 2,
                "max": 200,
                "description": "Kijun-sen / Chikou delay period.",
            },
            "span_b_period": {
                "type": "int",
                "default": 52,
                "min": 2,
                "max": 400,
                "description": "Senkou Span B lookback period.",
            },
        }

    @property
    def warmup_periods(self) -> int:
        return self._default_span_b - 1  # 51

    @property
    def output_names(self) -> List[str]:
        return [
            "conversion_line",
            "base_line",
            "span_a",
            "span_b",
            "lagging_span",
        ]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        conv = parameters.get_int("conversion_period", self._default_conversion)
        base = parameters.get_int("base_period", self._default_base)
        span_b = parameters.get_int("span_b_period", self._default_span_b)
        if conv < 2 or base < 2 or span_b < 2:
            raise ValueError("Ichimoku periods must be >= 2")
        return IndicatorParameters(
            values={
                "conversion_period": conv,
                "base_period": base,
                "span_b_period": span_b,
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
        conv = parameters.get_int("conversion_period", self._default_conversion)
        base = parameters.get_int("base_period", self._default_base)
        span_b = parameters.get_int("span_b_period", self._default_span_b)

        n = len(candles)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]

        conversion_line: List[Optional[Decimal]] = []
        base_line: List[Optional[Decimal]] = []
        span_a: List[Optional[Decimal]] = []
        span_b_series: List[Optional[Decimal]] = []
        lagging_span: List[Optional[Decimal]] = []

        for i in range(n):
            # Conversion line (window i-conv+1 .. i).
            if i >= conv - 1:
                hh = _highest_high(highs, i - conv + 1, i)
                ll = _lowest_low(lows, i - conv + 1, i)
                conv_val = (hh + ll) / _TWO
            else:
                conv_val = None
            conversion_line.append(conv_val)

            # Base line (window i-base+1 .. i).
            if i >= base - 1:
                hh = _highest_high(highs, i - base + 1, i)
                ll = _lowest_low(lows, i - base + 1, i)
                base_val = (hh + ll) / _TWO
            else:
                base_val = None
            base_line.append(base_val)

            # Span A = (conversion + base) / 2, causal (not forward displaced).
            if conv_val is not None and base_val is not None:
                span_a.append((conv_val + base_val) / _TWO)
            else:
                span_a.append(None)

            # Span B (window i-span_b+1 .. i), causal.
            if i >= span_b - 1:
                hh = _highest_high(highs, i - span_b + 1, i)
                ll = _lowest_low(lows, i - span_b + 1, i)
                span_b_series.append((hh + ll) / _TWO)
            else:
                span_b_series.append(None)

            # Lagging span = close delayed by `base` (causal).
            if i >= base:
                lagging_span.append(closes[i - base])
            else:
                lagging_span.append(None)

        # First fully valid index: need Span B window complete.
        first_valid = span_b - 1
        warmup = first_valid
        values: Dict[str, List[Optional[Decimal]]] = {
            "conversion_line": conversion_line,
            "base_line": base_line,
            "span_a": span_a,
            "span_b": span_b_series,
            "lagging_span": lagging_span,
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
                "formula": "Ichimoku Cloud (causal, no forward displacement)",
                "conversion_period": conv,
                "base_period": base,
                "span_b_period": span_b,
                "look_ahead": "none - spans not forward-displaced; lagging span is delayed close",
                "first_valid_index": first_valid,
            },
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
