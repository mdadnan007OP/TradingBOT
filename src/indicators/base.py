"""Base indicator interface and shared types.

Defines the common contract every indicator implements, plus the immutable
result and parameter models used across the engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from src.market_data.models import (
    DataSource,
    InstrumentType,
    MarketTimeframe,
    OHLCBar,
)


class ReadinessStatus(str, Enum):
    """Readiness of an indicator result for a given candle slice."""

    READY = "ready"
    """Enough data for a complete, stable calculation."""

    WARMING_UP = "warming_up"
    """Some values produced but not yet at full stability (warm-up window)."""

    INSUFFICIENT = "insufficient"
    """Too little data to produce any meaningful value."""

    INVALID = "invalid"
    """Input data was invalid; result should not be trusted."""


@dataclass(frozen=True)
class IndicatorParameters:
    """Immutable parameters for an indicator calculation.

    Accessors return typed defaults when a key is missing or unparseable,
    so callers never have to guard against missing parameters.
    """

    values: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def get_int(self, key: str, default: int) -> int:
        try:
            return int(self.values.get(key, default))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float) -> float:
        try:
            return float(self.values.get(key, default))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool) -> bool:
        raw = self.values.get(key, default)
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("true", "1", "yes", "on")


@dataclass(frozen=True)
class IndicatorResult:
    """Standardized output of an indicator calculation.

    ``values`` maps each output field name to a list aligned 1:1 with the
    input candles. Entry ``i`` corresponds to input candle ``i``. Entries
    are ``None`` when the indicator is not yet ready (warm-up) or the value
    is undefined.
    """

    symbol: str
    instrument_type: InstrumentType
    timeframe: MarketTimeframe
    indicator_name: str
    parameters: IndicatorParameters
    calculation_timestamp: datetime
    source_candle_timestamp: datetime
    data_source: DataSource
    values: Dict[str, List[Optional[Decimal]]]
    readiness: ReadinessStatus
    warmup_periods: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def output_names(self) -> List[str]:
        """Names of the output fields produced by this indicator."""
        return list(self.values.keys())

    @property
    def bar_count(self) -> int:
        """Number of candles represented in the result."""
        if not self.values:
            return 0
        return len(next(iter(self.values.values())))

    def last_value(self, output_name: str) -> Optional[Decimal]:
        """Return the most recent value for ``output_name``, or None."""
        series = self.values.get(output_name)
        if not series:
            return None
        return series[-1]


class Indicator(ABC):
    """Common interface every indicator must implement.

    Indicators are stateless: ``calculate`` receives candles and returns a new
    ``IndicatorResult`` without mutating inputs.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique indicator identifier (e.g. ``SMA``, ``RSI``)."""

    @property
    @abstractmethod
    def default_parameters(self) -> IndicatorParameters:
        """Sensible default parameter values."""

    @property
    @abstractmethod
    def parameter_schema(self) -> Dict[str, Dict[str, Any]]:
        """Describe supported parameters: name -> {type, default, min, max, description}."""

    @property
    @abstractmethod
    def warmup_periods(self) -> int:
        """Minimum number of candles before the indicator produces values."""

    @property
    @abstractmethod
    def output_names(self) -> List[str]:
        """Names of output fields produced by this indicator."""

    @abstractmethod
    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        """Validate and normalize parameters, raising ValueError on invalid config."""

    @abstractmethod
    def calculate(
        self,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
    ) -> IndicatorResult:
        """Calculate indicator values for the given candles.

        Returns an IndicatorResult aligned 1:1 with input candles.
        """
