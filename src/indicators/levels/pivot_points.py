"""Classic Pivot Points (support/resistance levels).

Uses the previous completed period's High/Low/Close — never future data.

Formula (classic):
    PP   = (H_prev + L_prev + C_prev) / 3
    R1   = 2 * PP - L_prev
    S1   = 2 * PP - H_prev
    R2   = PP + (H_prev - L_prev)
    S2   = PP - (H_prev - L_prev)
    R3   = H_prev + 2 * (PP - L_prev)
    S3   = L_prev - 2 * (H_prev - PP)

Period granularity:
    * ``daily``   — pivot computed from the previous UTC day's H/L/C.
    * ``weekly``  — pivot computed from the previous ISO week's H/L/C.

The pivot value is constant for every candle within the current period and is
derived solely from the *previous* completed period, so there is no look-ahead.

Outputs: ``pivot``, ``r1``, ``s1``, ``r2``, ``s2``, ``r3``, ``s3``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

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
_THREE = Decimal(3)


def _period_key(timestamp: datetime, granularity: str) -> Tuple:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if granularity == "weekly":
        iso = timestamp.isocalendar()
        return ("weekly", iso.year, iso.week)
    return ("daily", timestamp.date())


class _PeriodAgg:
    """Aggregates H/L/C for a single period."""

    __slots__ = ("key", "high", "low", "close", "first_ts", "last_ts", "bar_indices")

    def __init__(self, key: Tuple, first_ts: datetime) -> None:
        self.key = key
        self.high: Optional[Decimal] = None
        self.low: Optional[Decimal] = None
        self.close: Optional[Decimal] = None
        self.first_ts = first_ts
        self.last_ts = first_ts
        self.bar_indices: List[int] = []

    def update(self, high: Decimal, low: Decimal, close: Decimal, ts: datetime, idx: int) -> None:
        self.high = high if self.high is None else max(self.high, high)
        self.low = low if self.low is None else min(self.low, low)
        self.close = close
        self.last_ts = ts
        self.bar_indices.append(idx)

    @property
    def complete(self) -> bool:
        return self.high is not None and self.low is not None and self.close is not None


class ClassicPivotPointsIndicator(Indicator):
    """Classic Pivot Points based on the previous completed period."""

    name = "Classic Pivot Points"

    def __init__(self) -> None:
        self._default_granularity = "daily"

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={"granularity": self._default_granularity})

    @property
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        return {
            "granularity": {
                "type": "str",
                "default": "daily",
                "options": ["daily", "weekly"],
                "description": "Period granularity for the previous-completed-period calculation.",
            }
        }

    @property
    def warmup_periods(self) -> int:
        return 1  # need at least one previous completed period.

    @property
    def output_names(self) -> List[str]:
        return ["pivot", "r1", "s1", "r2", "s2", "r3", "s3"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        granularity = str(parameters.get("granularity", self._default_granularity)).lower()
        if granularity not in ("daily", "weekly"):
            raise ValueError("granularity must be 'daily' or 'weekly'")
        return IndicatorParameters(values={"granularity": granularity})

    def calculate(
        self,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
    ) -> IndicatorResult:
        if parameters is None:
            parameters = self.default_parameters
        parameters = self.validate_parameters(parameters)
        granularity = str(parameters.get("granularity", self._default_granularity)).lower()

        n = len(candles)
        if n == 0:
            return self._empty(parameters, granularity)

        # 1. Group candles into periods and aggregate H/L/C.
        periods: List[_PeriodAgg] = []
        bar_period_index: List[Optional[int]] = [None] * n
        current_key: Optional[Tuple] = None
        current_agg: Optional[_PeriodAgg] = None

        for i, c in enumerate(candles):
            key = _period_key(c.timestamp, granularity)
            if current_agg is None or key != current_key:
                current_agg = _PeriodAgg(key, c.timestamp)
                periods.append(current_agg)
                current_key = key
            current_agg.update(c.high, c.low, c.close, c.timestamp, i)
            bar_period_index[i] = len(periods) - 1

        # 2. Compute pivot values per period from the previous period's HLC.
        #    period_pivots[p] = dict of level -> value, or None if p == 0.
        period_pivots: List[Optional[Dict[str, Decimal]]] = []
        for p, agg in enumerate(periods):
            if p == 0 or not agg.complete:
                period_pivots.append(None)
                continue
            prev = periods[p - 1]
            if not prev.complete:
                period_pivots.append(None)
                continue
            h, l, c = prev.high, prev.low, prev.close
            pp = (h + l + c) / _THREE
            rng = h - l
            levels = {
                "pivot": pp,
                "r1": _TWO * pp - l,
                "s1": _TWO * pp - h,
                "r2": pp + rng,
                "s2": pp - rng,
                "r3": h + _TWO * (pp - l),
                "s3": l - _TWO * (h - pp),
            }
            period_pivots.append(levels)

        # 3. Assign pivot values to each candle from its period's pivot.
        nan = _ZERO  # placeholder
        pivot_lists: Dict[str, List[Optional[Decimal]]] = {
            name: [None] * n for name in self.output_names
        }
        for i in range(n):
            p = bar_period_index[i]
            levels = period_pivots[p] if p is not None else None
            if levels is None:
                continue
            for name in self.output_names:
                pivot_lists[name][i] = levels[name]

        # Readiness: ready once at least one candle has pivot values (i.e. a
        # second completed period exists).
        any_pivot = any(
            pivot_lists["pivot"][i] is not None for i in range(n)
        )
        if n < 2:
            readiness = ReadinessStatus.INSUFFICIENT
        elif not any_pivot:
            readiness = ReadinessStatus.INSUFFICIENT
        else:
            readiness = ReadinessStatus.READY

        first_valid = next(
            (i for i in range(n) if pivot_lists["pivot"][i] is not None), None
        )

        return IndicatorResult(
            symbol=candles[0].symbol,
            instrument_type=InstrumentType.FOREX,
            timeframe=candles[0].timeframe,
            indicator_name=self.name,
            parameters=parameters,
            calculation_timestamp=self._now(),
            source_candle_timestamp=candles[-1].timestamp,
            data_source=DataSource.SIMULATED,
            values=pivot_lists,
            readiness=readiness,
            warmup_periods=1,
            metadata={
                "formula": "Classic Pivot Points from previous completed period",
                "pp": "(H + L + C) / 3",
                "r1": "2*PP - L; s1: 2*PP - H",
                "r2": "PP + (H - L); s2: PP - (H - L)",
                "r3": "H + 2*(PP - L); s3: L - 2*(H - PP)",
                "granularity": granularity,
                "look_ahead": "none - uses previous completed period only",
                "first_valid_index": first_valid,
            },
        )

    def _empty(
        self, parameters: IndicatorParameters, granularity: str
    ) -> IndicatorResult:
        empty: Dict[str, List[Optional[Decimal]]] = {
            name: [] for name in self.output_names
        }
        return IndicatorResult(
            symbol="",
            instrument_type=InstrumentType.FOREX,
            timeframe=MarketTimeframe.M1,
            indicator_name=self.name,
            parameters=parameters,
            calculation_timestamp=self._now(),
            source_candle_timestamp=self._now(),
            data_source=DataSource.SIMULATED,
            values=empty,
            readiness=ReadinessStatus.INSUFFICIENT,
            warmup_periods=1,
            metadata={"granularity": granularity},
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
