"""Shared data models for strategy configuration and confirmation rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.indicators.base import IndicatorParameters
from src.market_data.models import DataSource, MarketTimeframe


@dataclass(frozen=True)
class ConfirmationCondition:
    """A single confirmation condition that must be satisfied.

    Attributes:
        indicator: Indicator name (e.g. ``RSI``, ``ADX``).
        output: Output field within the indicator result.
        operator: Comparison operator (``gt``, ``lt``, ``eq``, ``crosses_above``,
            ``crosses_below``, ``between``).
        value: Comparison value (single number, or tuple for ``between``).
        timeframe: Timeframe on which to evaluate (optional; defaults to
            strategy's entry timeframe).
        required: Whether this condition must be met (True) or is optional.
    """

    indicator: str
    output: str
    operator: str
    value: Any
    timeframe: Optional[MarketTimeframe] = None
    required: bool = True


@dataclass(frozen=True)
class ConfirmationRule:
    """A named group of confirmation conditions.

    Attributes:
        name: Human-readable rule name.
        conditions: List of conditions.
        min_required: Minimum number of conditions that must be satisfied
            (default: all required conditions).
        weight: Relative weight of this rule in aggregation (default 1.0).
    """

    name: str
    conditions: List[ConfirmationCondition]
    min_required: int = 1
    weight: float = 1.0


@dataclass(frozen=True)
class StrategyParameters:
    """Immutable strategy parameters.

    Wraps IndicatorParameters with strategy-specific fields like
    confirmation rules and timeframe mapping.
    """

    values: Dict[str, Any] = field(default_factory=dict)
    confirmation_rules: List[ConfirmationRule] = field(default_factory=list)
    entry_timeframe: Optional[MarketTimeframe] = None
    confirmation_timeframes: List[MarketTimeframe] = field(default_factory=list)
    min_confirmations: int = 1
    max_signal_age_minutes: int = 60
    technical_invalidation_buffer: Optional[float] = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def get_int(self, key: str, default: int) -> int:
        try:
            return int(self.values.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float) -> float:
        try:
            return float(self.values.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool) -> bool:
        raw = self.values.get(key, default)
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("true", "1", "yes", "on")

    def to_indicator_parameters(self) -> IndicatorParameters:
        """Convert to IndicatorParameters for indicator calculations."""
        return IndicatorParameters(values=dict(self.values))


@dataclass(frozen=True)
class IndicatorSnapshot:
    """A snapshot of indicator values at signal time."""

    indicator_name: str
    timeframe: MarketTimeframe
    outputs: Dict[str, List[Optional[float]]]
    readiness: str
    parameters: Dict[str, Any]


@dataclass(frozen=True)
class SignalValidationResult:
    """Result of validating signal prerequisites before analysis.

    All checks must pass for a signal to be considered valid. Any failure
    produces a rejection with an explicit category and reason.
    """

    valid: bool
    """Whether all validation checks passed."""

    category: Optional[str]
    """Failure category if invalid (see SignalRejection.category values)."""

    reason: Optional[str]
    """Human-readable failure reason if invalid."""

    candle_count: int
    """Number of candles available for analysis."""

    missing_indicators: List[str]
    """Indicator names that were unavailable or not ready."""

    stale_data_seconds: Optional[int]
    """Age of the most recent candle in seconds, if determinable."""


@dataclass(frozen=True)
class RiskInterfaceSignal:
    """Standardized interface for passing signals to Phase 6 Risk Management.

    Phase 5 produces this structure; Phase 6 consumes it for risk evaluation,
    position sizing, and stop-loss/take-profit calculation. No order execution
    occurs at this boundary.
    """

    signal_id: str
    strategy_name: str
    strategy_version: str
    config_fingerprint: str
    symbol: str
    instrument_type: str
    direction: str
    """LONG, SHORT, or NONE."""

    signal_timestamp: datetime
    signal_valid_until: Optional[datetime]
    market_data_timestamp: datetime
    reference_price: Optional[Decimal]
    technical_invalidation: Optional[Decimal]
    market_regime: str
    confirmation_conditions: List[str]
    failed_conditions: List[str]
    explanation: str
    expiry_conditions: List[str]
    data_source: str
    indicator_snapshot: Dict[str, List[Optional[Decimal]]]
    parameters: Dict[str, Any]
    entry_timeframe: str
    confirmation_timeframes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for JSON or Phase 6 consumption."""
        return {
            "signal_id": self.signal_id,
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "config_fingerprint": self.config_fingerprint,
            "symbol": self.symbol,
            "instrument_type": self.instrument_type,
            "direction": self.direction,
            "signal_timestamp": self.signal_timestamp.isoformat(),
            "signal_valid_until": (
                self.signal_valid_until.isoformat()
                if self.signal_valid_until else None
            ),
            "market_data_timestamp": self.market_data_timestamp.isoformat(),
            "reference_price": str(self.reference_price)
            if self.reference_price is not None else None,
            "technical_invalidation": (
                str(self.technical_invalidation)
                if self.technical_invalidation is not None else None
            ),
            "market_regime": self.market_regime,
            "confirmation_conditions": self.confirmation_conditions,
            "failed_conditions": self.failed_conditions,
            "explanation": self.explanation,
            "expiry_conditions": self.expiry_conditions,
            "data_source": self.data_source,
            "indicator_snapshot": {
                k: [str(v) if v is not None else None for v in vals]
                for k, vals in self.indicator_snapshot.items()
            },
            "parameters": self.parameters,
            "entry_timeframe": self.entry_timeframe,
            "confirmation_timeframes": [tf.value for tf in self.confirmation_timeframes],
        }


def compute_config_fingerprint(parameters: Dict[str, Any]) -> str:
    """Compute a SHA-256 fingerprint of strategy parameters for reproducibility.

    The fingerprint allows historical signals to be traced back to the exact
    parameter configuration that generated them, even if parameter values
    change over time.
    """
    canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
