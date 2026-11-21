"""Strategy Engine base module — signal model and strategy interface.

Phase 5 is a signal-generation phase only. Strategies produce standardized
``Signal`` objects (LONG / SHORT / NONE) with full provenance. No order
placement, order modification, or position closing is performed here.

All strategies are:
- Stateless: ``analyze`` returns a new ``Signal`` without mutating inputs.
- Source-aware: results carry ``data_source`` provenance.
- Look-ahead safe: completed candles are used by default.
- Independently configurable, testable, enableable and disableable.
"""

from __future__ import annotations

import abc
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

ABC = abc.ABC
abstractmethod = abc.abstractmethod

from src.indicators.base import IndicatorParameters, ReadinessStatus
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar


class SignalDirection(str, Enum):
    """Direction of a trading signal."""

    LONG = "LONG"
    """Bullish signal — buy bias."""

    SHORT = "SHORT"
    """Bearish signal — sell bias."""

    NONE = "NONE"
    """No actionable signal."""


class SignalStatus(str, Enum):
    """Lifecycle status of a signal."""

    ACTIVE = "ACTIVE"
    """Signal is currently valid and actionable."""

    EXPIRED = "EXPIRED"
    """Signal has passed its expiry conditions."""

    REJECTED = "REJECTED"
    """Signal was rejected due to validation failure."""

    NO_SIGNAL = "NO_SIGNAL"
    """Analysis completed but no signal meets the entry criteria."""


class MarketRegime(str, Enum):
    """Market regime classification."""

    TRENDING = "TRENDING"
    """Directional market with sustained momentum."""

    RANGING = "RANGING"
    """Sideways market within bounded support/resistance."""

    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    """Elevated volatility environment."""

    LOW_VOLATILITY = "LOW_VOLATILITY"
    """Compressed volatility environment."""

    TRANSITIONING = "TRANSITIONING"
    """Market shifting between regimes."""

    UNKNOWN = "UNKNOWN"
    """Insufficient data to classify."""


@dataclass(frozen=True)
class Signal:
    """Standardized trading signal output.

    A signal is a structured recommendation, not an order. It carries full
    provenance so downstream phases (risk management, execution) can evaluate
    it without re-deriving the analysis.

    Lifecycle:
        * Created with status ACTIVE and a signal_valid_until timestamp.
        * Can transition to EXPIRED when signal_valid_until is reached.
        * Can transition to REJECTED if validation fails.
        * Can be invalidated by price crossing technical_invalidation.
        * Duplicate detection via duplicate_key (strategy + symbol + timeframe +
          candle timestamp).
    """

    signal_id: str
    """Unique identifier for this signal."""

    strategy_name: str
    """Name of the strategy that generated the signal."""

    strategy_version: str
    """Version string of the strategy implementation."""

    symbol: str
    """Trading instrument (e.g. ``XAUUSD``)."""

    instrument_type: str
    """Asset class (forex, metal, energy, index, crypto, equity, other)."""

    direction: SignalDirection
    """LONG, SHORT, or NONE."""

    status: SignalStatus
    """Current lifecycle status."""

    entry_timeframe: MarketTimeframe
    """Timeframe on which the entry condition was evaluated."""

    confirmation_timeframes: List[MarketTimeframe]
    """Additional timeframes used to confirm the signal."""

    signal_timestamp: datetime
    """When the signal was generated (UTC)."""

    market_data_timestamp: datetime
    """Timestamp of the last candle used in analysis (UTC)."""

    reference_price: Optional[Decimal]
    """Reference entry price, where applicable (e.g. candle close)."""

    technical_invalidation: Optional[Decimal]
    """Price level that invalidates the setup (NOT a stop-loss)."""

    parameters: IndicatorParameters
    """Strategy parameters used for this signal."""

    indicator_snapshot: Dict[str, List[Optional[Decimal]]]
    """Indicator values at signal time, keyed by output name."""

    market_regime: MarketRegime
    """Regime classification at signal time."""

    confirmation_conditions: List[str]
    """Human-readable list of conditions that were satisfied."""

    explanation: str
    """Human-readable explanation of why the signal was generated."""

    expiry_conditions: List[str]
    """Conditions under which the signal expires."""

    data_source: DataSource
    """Provenance of the underlying market data."""

    strategy_validity_state: str
    """Strategy validity state (e.g. 'valid', 'suspended', 'disabled')."""

    config_fingerprint: str = ""
    """SHA-256 fingerprint of the strategy parameters for reproducibility."""

    signal_valid_until: Optional[datetime] = None
    """When the signal expires (None = no explicit expiry)."""

    failed_conditions: List[str] = field(default_factory=list)
    """Human-readable list of conditions that were checked but not satisfied."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional strategy-specific metadata."""

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    @property
    def duplicate_key(self) -> str:
        """Stable key for duplicate detection.

        Combines strategy, symbol, timeframe, and market data timestamp so
        the same strategy cannot emit a duplicate signal for the same candle
        unless conditions change.
        """
        parts = [
            self.strategy_name,
            self.symbol,
            self.entry_timeframe.value,
            str(self.market_data_timestamp),
        ]
        return "|".join(parts)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Return True if the signal has passed its validity period."""
        if self.signal_valid_until is None:
            return False
        check_time = now or datetime.now(timezone.utc)
        return check_time >= self.signal_valid_until

    def is_invalidated(self, current_price: Decimal) -> bool:
        """Return True if price has crossed the technical invalidation level.

        For LONG signals: invalidated when price <= technical_invalidation.
        For SHORT signals: invalidated when price >= technical_invalidation.
        """
        if self.technical_invalidation is None:
            return False
        if self.direction == SignalDirection.LONG:
            return current_price <= self.technical_invalidation
        if self.direction == SignalDirection.SHORT:
            return current_price >= self.technical_invalidation
        return False

    def is_actionable(self, now: Optional[datetime] = None) -> bool:
        """Return True if the signal is ACTIVE, not expired, and not invalidated
        (invalidation requires a price, so this only checks status + expiry)."""
        if self.status != SignalStatus.ACTIVE:
            return False
        if self.direction == SignalDirection.NONE:
            return False
        return not self.is_expired(now)


@dataclass(frozen=True)
class SignalRejection:
    """A rejected signal with an explicit reason.

    Rejections are never silently discarded — every rejection carries a
    machine-readable category and a human-readable explanation.
    """

    symbol: str
    timeframe: MarketTimeframe
    strategy_name: str
    reason: str
    """Human-readable explanation of why the signal was rejected."""
    data_source: DataSource
    timestamp: datetime
    category: str = "unknown"
    """Machine-readable category: 'insufficient_data', 'invalid_ohlc',
    'incomplete_candle', 'stale_data', 'unsupported_timeframe',
    'unavailable_indicator', 'invalid_configuration', 'regime_unsupported',
    'strategy_error', 'duplicate_signal', 'no_signal_condition'."""
    candle_count: Optional[int] = None
    """Number of candles available at rejection time (for debugging)."""
    missing_indicators: List[str] = field(default_factory=list)
    """Indicator names that were unavailable or not ready."""


@dataclass(frozen=True)
class StrategyResult:
    """Result of running one strategy on one symbol/timeframe."""

    strategy_name: str
    symbol: str
    timeframe: MarketTimeframe
    signals: List[Signal]
    rejections: List[SignalRejection]
    market_regime: MarketRegime
    indicator_snapshots: Dict[str, IndicatorParameters]
    error: Optional[str] = None
    """If set, the strategy encountered an error and signals may be incomplete."""
    validation_passed: bool = True
    """Whether pre-analysis validation (candles, OHLC, completeness) passed."""

    @property
    def active_signals(self) -> List[Signal]:
        """Return signals with ACTIVE status."""
        return [s for s in self.signals if s.status == SignalStatus.ACTIVE]

    @property
    def long_signals(self) -> List[Signal]:
        return [s for s in self.active_signals if s.direction == SignalDirection.LONG]

    @property
    def short_signals(self) -> List[Signal]:
        return [s for s in self.active_signals if s.direction == SignalDirection.SHORT]

    @property
    def actionable_signals(self, now: Optional[datetime] = None) -> List[Signal]:
        """Return signals that are ACTIVE, not expired, and not invalidated."""
        return [s for s in self.signals if s.is_actionable(now)]


class Strategy(ABC):
    """Base class for all trading strategies.

    Strategies are independent, testable, enableable and disableable.
    ``analyze`` receives validated candles and an indicator engine, and
    returns a ``StrategyResult``. It never places orders.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier (e.g. ``TrendFollowing``)."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Strategy version string."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether the strategy is currently enabled."""

    @property
    @abstractmethod
    def required_timeframes(self) -> List[MarketTimeframe]:
        """Timeframes this strategy needs to operate."""

    @property
    @abstractmethod
    def supported_instruments(self) -> Optional[List[str]]:
        """Instrument symbols this strategy supports, or None for all."""

    @property
    @abstractmethod
    def supported_regimes(self) -> List[MarketRegime]:
        """Market regimes in which this strategy produces signals."""

    @property
    @abstractmethod
    def default_parameters(self) -> IndicatorParameters:
        """Default strategy parameters."""

    @abstractmethod
    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        """Validate and normalize parameters."""

    @abstractmethod
    def analyze(
        self,
        symbol: str,
        candles_by_timeframe: Dict[MarketTimeframe, List[OHLCBar]],
        indicator_engine: Any,
        parameters: Optional[IndicatorParameters] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> StrategyResult:
        """Analyze market data and produce signals.

        Args:
            symbol: Trading instrument.
            candles_by_timeframe: Candles keyed by timeframe.
            indicator_engine: IndicatorEngine instance for calculations.
            parameters: Strategy parameters (defaults if omitted).
            data_source: Provenance of the market data.

        Returns:
            StrategyResult with signals, rejections, and regime.
        """
        ...

    def enable(self) -> None:
        """Enable the strategy."""

    def disable(self) -> None:
        """Disable the strategy."""


@dataclass(frozen=True)
class SignalGenerationContext:
    """Context passed to strategies during analysis."""

    symbol: str
    candles_by_timeframe: Dict[MarketTimeframe, List[OHLCBar]]
    indicator_engine: Any
    parameters: IndicatorParameters
    data_source: DataSource
    calculation_timestamp: datetime
