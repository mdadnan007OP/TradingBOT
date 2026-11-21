"""ADX — Average Directional Index (trend indicator).

Measures trend strength (not direction). Uses Wilder's smoothing.

Components:
    +DM_t = High_t - High_{t-1}  if up move > down move and > 0, else 0
    -DM_t = Low_{t-1} - Low_t    if down move > up move and > 0, else 0
    TR_t  = max(High - Low, |High - PrevClose|, |Low - PrevClose|)
    Smoothed TR / +DM / -DM via Wilder smoothing over ``period``.
    +DI_t = 100 * Smoothed +DM / Smoothed TR
    -DI_t = 100 * Smoothed -DM / Smoothed TR
    DX_t  = 100 * |+DI - -DI| / (+DI + -DI)
    ADX_t = Wilder-smoothed DX over ``period``.

Zero denominators: when Smoothed TR == 0, +DI/-DI = 0. When +DI + -DI == 0,
DX = 0.

Warm-up: roughly ``2 * period - 1`` candles before the first ADX value.
Default period: ``14``.

Outputs: ``adx``, ``plus_di``, ``minus_di``.
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
from src.indicators.calculator import (
    true_range,
    wilder_smooth,
)
from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)


class ADXIndicator(Indicator):
    """Average Directional Index (trend strength)."""

    name = "ADX"

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
                "description": "Wilder smoothing period for ADX.",
            }
        }

    @property
    def warmup_periods(self) -> int:
        return 2 * self._default_period  # conservative upper bound

    @property
    def output_names(self) -> List[str]:
        return ["adx", "plus_di", "minus_di"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        period = parameters.get_int("period", self._default_period)
        if period < 2:
            raise ValueError("ADX period must be >= 2")
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

        # True Range and directional movement per bar (bar 0 has no prev close).
        trs: List[Decimal] = []
        plus_dm: List[Decimal] = []
        minus_dm: List[Decimal] = []
        for i in range(n):
            if i == 0:
                trs.append(highs[0] - lows[0])
                plus_dm.append(_ZERO)
                minus_dm.append(_ZERO)
            else:
                up_move = highs[i] - highs[i - 1]
                down_move = lows[i - 1] - lows[i]
                plus_d = _ZERO
                minus_d = _ZERO
                if up_move > down_move and up_move > 0:
                    plus_d = up_move
                elif down_move > up_move and down_move > 0:
                    minus_d = down_move
                # If up_move == down_move (or both <= 0), both are 0 (inside bar).
                trs.append(true_range(highs[i], lows[i], closes[i - 1]))
                plus_dm.append(plus_d)
                minus_dm.append(minus_d)

        # Wilder smoothing over `period`. First smoothed value at index period-1
        # (sum of first `period` values), but our arrays start at bar 0.
        # We align smoothed series with candle indices; bar 0 has no prev close,
        # so meaningful smoothing starts from bar 1.
        smooth_tr = wilder_smooth(trs, period)
        smooth_plus = wilder_smooth(plus_dm, period)
        smooth_minus = wilder_smooth(minus_dm, period)

        # +DI / -DI / DX per bar.
        plus_di: List[Optional[Decimal]] = []
        minus_di: List[Optional[Decimal]] = []
        dx: List[Optional[Decimal]] = []
        for i in range(n):
            tr = smooth_tr[i]
            sp = smooth_plus[i]
            sm = smooth_minus[i]
            if tr is None or tr == 0:
                plus_di.append(_ZERO)
                minus_di.append(_ZERO)
                dx.append(_ZERO)
            else:
                pd = (_HUNDRED * sp / tr) if sp is not None else _ZERO
                md = (_HUNDRED * sm / tr) if sm is not None else _ZERO
                plus_di.append(pd)
                minus_di.append(md)
                denom = pd + md
                if denom == 0:
                    dx.append(_ZERO)
                else:
                    dx.append(_HUNDRED * abs(pd - md) / denom)

        # ADX = Wilder smooth of DX over `period`.
        # Build a series where None positions are skipped by Wilder (they break
        # smoothing); here DX is never None (0 substituted), so smoothing works.
        dx_values: List[Decimal] = [d if d is not None else _ZERO for d in dx]
        smooth_dx = wilder_smooth(dx_values, period)

        adx: List[Optional[Decimal]] = []
        for i in range(n):
            v = smooth_dx[i]
            adx.append(v if v is not None else None)

        # Readiness: first ADX at index 2*period-1.
        first_valid = 2 * period - 1
        warmup = first_valid
        values: Dict[str, List[Optional[Decimal]]] = {
            "adx": adx,
            "plus_di": plus_di,
            "minus_di": minus_di,
        }
        if n <= warmup:
            readiness = ReadinessStatus.INSUFFICIENT
        elif n <= warmup + 1:
            readiness = ReadinessStatus.WARMING_UP
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
                "formula": "ADX = Wilder-smoothed DX over `period`",
                "dx": "100 * |+DI - -DI| / (+DI + -DI)",
                "smoothing": "Wilder",
                "period": period,
                "first_valid_index": first_valid,
            },
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
