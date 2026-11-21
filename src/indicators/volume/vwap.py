"""VWAP — Volume Weighted Average Price (volume indicator).

Formula:
    TP_t  = (High + Low + Close) / 3                     # typical price
    VWAP  = sum(TP * volume) / sum(volume) over session

Volume handling (Forex / MT5 aware):
    * MT5 volume is frequently *tick* volume, not real traded volume.
    * ``volume_source`` selects the basis: ``real``, ``tick``, or ``auto``.
    * ``auto`` prefers ``real_volume`` and falls back to ``tick_volume``.
    * The chosen basis is reported per candle in ``volume_basis`` and in
      result metadata, so tick-volume VWAP is never mistaken for real volume.
    * VWAP is ``None`` for any candle where the selected volume is missing or
      invalid (never manufactures volume).

Session resets:
    * ``daily``   — cumulative sums reset at each UTC day boundary.
    * ``weekly``  — cumulative sums reset at each ISO week boundary.
    * ``none``    — no reset (cumulative over the full history).

Default parameters: volume_source=auto, session_reset=daily.
Outputs: ``vwap``, ``volume_basis``.
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


def _session_key(timestamp: datetime, reset: str) -> Tuple:
    """Return a session-boundary key for a timestamp."""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if reset == "daily":
        return ("daily", timestamp.date())
    if reset == "weekly":
        iso = timestamp.isocalendar()
        return ("weekly", iso.year, iso.week)
    return ("none",)


class VWAPIndicator(Indicator):
    """Volume Weighted Average Price with session resets."""

    name = "VWAP"

    def __init__(self) -> None:
        self._default_volume_source = "auto"
        self._default_session_reset = "daily"

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(
            values={
                "volume_source": self._default_volume_source,
                "session_reset": self._default_session_reset,
            }
        )

    @property
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        return {
            "volume_source": {
                "type": "str",
                "default": "auto",
                "options": ["real", "tick", "auto"],
                "description": "Volume basis: 'real' (real_volume), 'tick' (tick_volume), or 'auto' (prefer real, fall back to tick).",
            },
            "session_reset": {
                "type": "str",
                "default": "daily",
                "options": ["daily", "weekly", "none"],
                "description": "When to reset cumulative VWAP sums.",
            },
        }

    @property
    def warmup_periods(self) -> int:
        return 0  # VWAP produces a value as soon as volume is available.

    @property
    def output_names(self) -> List[str]:
        return ["vwap", "volume_basis"]

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        vs = str(parameters.get("volume_source", self._default_volume_source)).lower()
        sr = str(parameters.get("session_reset", self._default_session_reset)).lower()
        if vs not in ("real", "tick", "auto"):
            raise ValueError("volume_source must be 'real', 'tick', or 'auto'")
        if sr not in ("daily", "weekly", "none"):
            raise ValueError("session_reset must be 'daily', 'weekly', or 'none'")
        return IndicatorParameters(
            values={"volume_source": vs, "session_reset": sr}
        )

    def _select_volume(
        self,
        vs: str,
        bar: OHLCBar,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Return (volume, basis) for a bar given the volume source.

        basis is "real", "tick", or None.
        """
        if vs == "real":
            if bar.real_volume is not None and bar.real_volume > 0:
                return bar.real_volume, "real"
            return None, None
        if vs == "tick":
            if bar.tick_volume is not None and bar.tick_volume > 0:
                return bar.tick_volume, "tick"
            return None, None
        # auto: prefer real, fall back to tick.
        if bar.real_volume is not None and bar.real_volume > 0:
            return bar.real_volume, "real"
        if bar.tick_volume is not None and bar.tick_volume > 0:
            return bar.tick_volume, "tick"
        return None, None

    def calculate(
        self,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
    ) -> IndicatorResult:
        if parameters is None:
            parameters = self.default_parameters
        parameters = self.validate_parameters(parameters)
        vs = str(parameters.get("volume_source", self._default_volume_source)).lower()
        sr = str(parameters.get("session_reset", self._default_session_reset)).lower()

        n = len(candles)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]

        typical = [(highs[i] + lows[i] + closes[i]) / Decimal(3) for i in range(n)]

        vwap: List[Optional[Decimal]] = []
        volume_basis: List[Optional[str]] = []
        cum_tp_vol = _ZERO
        cum_vol = _ZERO
        prev_session: Optional[Tuple] = None

        for i in range(n):
            session = _session_key(candles[i].timestamp, sr)
            if session != prev_session:
                # New session: reset cumulative sums.
                cum_tp_vol = _ZERO
                cum_vol = _ZERO
                prev_session = session

            volume, basis = self._select_volume(vs, candles[i])
            volume_basis.append(basis)

            if volume is None:
                # No usable volume for this candle: contributes nothing.
                vwap.append(None)
                continue

            cum_tp_vol += typical[i] * Decimal(volume)
            cum_vol += Decimal(volume)
            if cum_vol > 0:
                vwap.append(cum_tp_vol / cum_vol)
            else:
                vwap.append(None)

        # Readiness: VWAP is ready once at least one candle had usable volume.
        any_volume = any(b is not None for b in volume_basis)
        if n == 0:
            readiness = ReadinessStatus.INSUFFICIENT
        elif not any_volume:
            readiness = ReadinessStatus.INSUFFICIENT
        else:
            readiness = ReadinessStatus.READY

        values: Dict[str, List[Optional[Decimal]]] = {"vwap": vwap}
        # volume_basis is a list of strings, not Decimals; store in metadata
        # and also expose via values as None (values dict is Decimal-typed).
        # We include a parallel basis list in metadata for consumers.
        metadata = {
            "formula": "VWAP = sum(TP * volume) / sum(volume) over session",
            "tp": "(High + Low + Close) / 3",
            "volume_source": vs,
            "session_reset": sr,
            "volume_basis_per_bar": volume_basis,
            "tick_volume_warning": (
                "If volume_source is 'tick' or 'auto' falls back to tick, "
                "the volume basis is tick volume — NOT actual traded volume. "
                "Forex MT5 volume is frequently tick volume."
            ),
            "first_valid_index": next(
                (i for i, b in enumerate(volume_basis) if b is not None), None
            ),
        }

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
            warmup_periods=0,
            metadata=metadata,
        )

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
