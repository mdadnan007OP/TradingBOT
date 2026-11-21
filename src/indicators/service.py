"""Indicator calculation service (concrete IndicatorEngine).

Orchestrates indicator calculation via the centralized registry. Keeps
indicator formulas separate from orchestration logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.engines import IndicatorEngine as IndicatorEngineABC
from src.indicators.base import (
    Indicator,
    IndicatorParameters,
    IndicatorResult,
    ReadinessStatus,
)
from src.indicators.registry import IndicatorRegistry
from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)

logger = logging.getLogger(__name__)


class IndicatorEngine:
    """Computes technical indicators from validated OHLC candles.

    Responsibilities:
        * Receive standardized OHLC candles from the Market Data Engine.
        * Validate input data (timezone-aware, sorted, sufficient count).
        * Delegate calculation to the registered indicator implementation.
        * Return standardized :class:`IndicatorResult` objects carrying full
          provenance (symbol, timeframe, data source, parameters, timestamps).

    The engine is source-agnostic: it works with simulated, historical CSV,
    and MT5-originated candles without depending on the MetaTrader5 package.
    """

    def __init__(self, registry: Optional[IndicatorRegistry] = None) -> None:
        self._registry = registry or IndicatorRegistry()
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # ------------------------------------------------------------------
    # Registry access
    # ------------------------------------------------------------------

    @property
    def registry(self) -> IndicatorRegistry:
        """Return the underlying indicator registry."""
        return self._registry

    def register_indicator(self, indicator: Indicator) -> None:
        """Register an indicator implementation."""
        self._registry.register(indicator)

    def supported_indicators(self) -> List[str]:
        """Return all registered indicator names."""
        return self._registry.supported_indicators()

    def indicator_exists(self, name: str) -> bool:
        """Return True if ``name`` is registered."""
        return self._registry.exists(name)

    def parameter_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """Return the parameter schema for ``name``, or None if unknown."""
        return self._registry.parameter_schema(name)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_candles(
        symbol: str,
        timeframe: MarketTimeframe,
        candles: List[OHLCBar],
        allow_incomplete: bool = False,
    ) -> List[OHLCBar]:
        """Validate and normalize input candles.

        Returns a sorted, deduplicated list. Raises ValueError on invalid
        input. Incomplete candles are dropped unless ``allow_incomplete`` is
        True (in which case they are kept but flagged).
        """
        if not candles:
            raise ValueError(f"No candles provided for {symbol} {timeframe.value}")

        # Ensure all candles share symbol/timeframe.
        for c in candles:
            if c.symbol != symbol:
                raise ValueError(
                    f"Candle symbol {c.symbol!r} does not match requested {symbol!r}"
                )
            if c.timeframe != timeframe:
                raise ValueError(
                    f"Candle timeframe {c.timeframe.value} does not match requested {timeframe.value}"
                )
            if c.timestamp.tzinfo is None:
                raise ValueError(
                    f"Candle timestamp {c.timestamp} is not timezone-aware UTC"
                )

        # Sort chronologically and deduplicate by timestamp.
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        seen: set = set()
        unique: List[OHLCBar] = []
        for c in sorted_candles:
            if c.timestamp in seen:
                continue
            seen.add(c.timestamp)
            if not c.is_complete and not allow_incomplete:
                continue  # drop incomplete bars by default (no look-ahead)
            unique.append(c)

        if not unique:
            raise ValueError(
                f"No usable (complete) candles for {symbol} {timeframe.value}"
            )
        return unique

    # ------------------------------------------------------------------
    # Public API (rich result)
    # ------------------------------------------------------------------

    def calculate(
        self,
        name: str,
        symbol: str,
        timeframe: MarketTimeframe,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
        data_source: DataSource = DataSource.SIMULATED,
        instrument_type: Optional[InstrumentType] = None,
        allow_incomplete: bool = False,
        calculation_timestamp: Optional[datetime] = None,
    ) -> IndicatorResult:
        """Calculate ``name`` for ``symbol``/``timeframe`` candles.

        Returns an :class:`IndicatorResult` aligned 1:1 with the input
        candles. ``None`` values mark warm-up / insufficient-data positions.

        Args:
            name: Registered indicator name.
            symbol: Instrument symbol.
            timeframe: Candle timeframe.
            candles: Validated OHLC bars (chronological).
            parameters: Indicator parameters; defaults are used if omitted.
            data_source: Provenance of the input candles.
            instrument_type: Asset class; inferred from symbol spec if omitted.
            allow_incomplete: Whether to include incomplete candles.
            calculation_timestamp: Override for the result timestamp (now if None).

        Raises:
            ValueError: If the indicator is unknown, parameters are invalid,
                or candle input is invalid.
        """
        if not self._registry.exists(name):
            raise ValueError(f"Unknown indicator: {name!r}")

        indicator = self._registry.get(name)
        if indicator is None:  # pragma: no cover - defensive
            raise ValueError(f"Unknown indicator: {name!r}")

        if parameters is None:
            parameters = indicator.default_parameters
        else:
            parameters = indicator.validate_parameters(parameters)

        valid_candles = self._validate_candles(
            symbol, timeframe, candles, allow_incomplete=allow_incomplete
        )

        if instrument_type is None:
            instrument_type = InstrumentType.FOREX

        if calculation_timestamp is None:
            calculation_timestamp = datetime.now(timezone.utc)

        try:
            result = indicator.calculate(valid_candles, parameters)
        except Exception as exc:  # noqa: BLE001 - surface as ValueError
            self._logger.exception(
                "Indicator %s failed for %s %s", name, symbol, timeframe.value
            )
            raise ValueError(
                f"Indicator {name!r} calculation failed: {exc}"
            ) from exc

        # Enforce provenance and alignment on the returned result.
        result = IndicatorResult(
            symbol=symbol,
            instrument_type=instrument_type,
            timeframe=timeframe,
            indicator_name=name,
            parameters=parameters,
            calculation_timestamp=calculation_timestamp,
            source_candle_timestamp=valid_candles[-1].timestamp,
            data_source=data_source,
            values=result.values,
            readiness=result.readiness,
            warmup_periods=result.warmup_periods,
            metadata=result.metadata,
        )

        self._logger.debug(
            "Computed %s for %s %s: %d bars, readiness=%s",
            name,
            symbol,
            timeframe.value,
            result.bar_count,
            result.readiness.value,
        )
        return result

    # ------------------------------------------------------------------
    # IndicatorEngineABC compatibility (returns Dict[str, List[float]])
    # ------------------------------------------------------------------

    def compute(
        self,
        name: str,
        symbol: str,
        candles: List[OHLCBar],
        **params: Any,
    ) -> Dict[str, List[float]]:
        """Compatibility with :class:`src.engines.IndicatorEngine`.

        Returns ``Dict[output_name, List[float]]`` with ``None`` mapped to
        ``float("nan")``. The rich :meth:`calculate` is preferred.
        """
        # Derive a default timeframe from the first candle if available.
        if not candles:
            return {}
        timeframe = candles[0].timeframe

        # Convert plain params into IndicatorParameters.
        parameters = IndicatorParameters(values=dict(params))

        result = self.calculate(
            name=name,
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            parameters=parameters,
            data_source=DataSource.SIMULATED,
        )

        output: Dict[str, List[float]] = {}
        for out_name in result.output_names:
            series: List[float] = []
            for v in result.values.get(out_name, []):
                series.append(float("nan") if v is None else float(v))
            output[out_name] = series
        return output

    def supported_indicators_abc(self) -> List[str]:
        """Compatibility alias for supported_indicators."""
        return self.supported_indicators()
