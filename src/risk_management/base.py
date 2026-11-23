"""Risk Management Engine base module.

Phase 6 is a risk-evaluation phase only. It calculates, validates and reports
on proposed trade signals. It never places, modifies or closes orders.

All risk decisions are hypothetical: a RISK_APPROVED result means the proposal
passed configured risk checks. It does NOT authorize execution.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

ABC = abc.ABC
abstractmethod = abc.abstractmethod


class RiskDecisionStatus(str, Enum):
    """Standardized risk decision statuses."""

    APPROVED = "RISK_APPROVED"
    """The proposal passed all configured risk checks (hypothetical only)."""

    REJECTED = "RISK_REJECTED"
    """The proposal violates one or more risk policies."""

    REQUIRES_INFORMATION = "REQUIRES_INFORMATION"
    """Essential data is missing; cannot reach a decision safely."""

    LOCKED = "RISK_LOCKED"
    """Account/portfolio is locked by a circuit breaker or protection rule."""

    CALCULATION_UNAVAILABLE = "CALCULATION_UNAVAILABLE"
    """A calculation could not be completed (e.g. missing spec, stale data)."""


class SizingMethod(str, Enum):
    """Position sizing methods."""

    PERCENT_EQUITY = "percent_equity"
    """Risk a fixed percentage of account equity per trade."""

    FIXED_MONETARY = "fixed_monetary"
    """Risk a fixed monetary amount per trade."""


class StopMethod(str, Enum):
    """Stop-loss determination methods."""

    TECHNICAL_INVALIDATION = "technical_invalidation"
    """Strategy-provided technical invalidation level."""

    ATR_BASED = "atr_based"
    """ATR-based distance from entry."""

    SWING_STRUCTURE = "swing_structure"
    """Confirmed swing high/low structure."""

    FIXED_DISTANCE = "fixed_distance"
    """Fixed price distance, explicitly configured."""


class TakeProfitMethod(str, Enum):
    """Take-profit determination methods."""

    REWARD_TO_RISK = "reward_to_risk"
    """Multiple of stop distance (configured R:R)."""

    ATR_BASED = "atr_based"
    """ATR-based target distance."""

    TECHNICAL_TARGET = "technical_target"
    """Strategy-provided technical target."""

    SUPPORT_RESISTANCE = "support_resistance"
    """Support/resistance level target."""


class CircuitBreakerReason(str, Enum):
    """Reasons a circuit breaker may trigger."""

    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_DRAWDOWN = "max_drawdown"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    INVALID_ACCOUNT = "invalid_account"
    STALE_DATA = "stale_data"
    BROKER_CONNECTION_LOSS = "broker_connection_loss"
    INVALID_INSTRUMENT_SPEC = "invalid_instrument_spec"
    EXPOSURE_BREACH = "exposure_breach"
    CALCULATION_FAILURE = "calculation_failure"
    POLICY_INVALID = "policy_invalid"


@dataclass(frozen=True)
class RiskParameters:
    """Inputs for a single risk evaluation.

    All prices are reference/estimated prices, not guaranteed execution prices.
    """

    signal_id: str
    symbol: str
    instrument_type: str
    direction: str  # "LONG", "SHORT", or "NONE"
    reference_price: Optional[Decimal]
    """Reference entry price (e.g. candle close). Estimated, not guaranteed."""

    technical_invalidation: Optional[Decimal]
    """Strategy technical invalidation level (NOT a stop-loss)."""

    stop_loss_price: Optional[Decimal]
    take_profit_price: Optional[Decimal]
    stop_distance: Optional[Decimal]
    """Explicit stop distance in price units (used by fixed_distance method)."""

    atr_value: Optional[Decimal]
    atr_multiplier: Optional[Decimal]
    reward_to_risk: Optional[Decimal]
    swing_high: Optional[Decimal]
    swing_low: Optional[Decimal]
    account_currency: str = "USD"
    equity: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    free_margin: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    leverage: Optional[Decimal] = None
    spread: Optional[Decimal] = None
    slippage_estimate: Optional[Decimal] = None
    stop_method: Optional[str] = None
    tp_method: Optional[str] = None
    rates: Dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class PositionExposure:
    """Current or proposed exposure for a symbol/asset class."""

    symbol: str
    instrument_type: str
    direction: str
    volume: Decimal
    open_price: Decimal
    notional: Decimal
    """Volume × price × contract_size (in profit currency, before conversion)."""

    risk_amount: Decimal = Decimal("0")
    monetary_risk: Decimal = Decimal("0")
    asset_class: Optional[str] = None


@dataclass(frozen=True)
class AccountSnapshot:
    """Read-only account snapshot used for risk evaluation.

    Timestamps are timezone-aware UTC. Missing essential fields make the
    snapshot ineligible for precise calculations.
    """

    login: int
    name: str
    server: str
    currency: str
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Optional[Decimal] = None
    trade_allowed: bool = False
    trade_mode: str = "demo"
    leverage: Optional[Decimal] = None
    timestamp: Optional[datetime] = None
    data_source: str = "mock"

    def is_stale(self, max_age_seconds: int, reference_time: Optional[datetime] = None) -> bool:
        if self.timestamp is None:
            return True
        ref = reference_time or datetime.now(timezone.utc)
        age = (ref - self.timestamp).total_seconds()
        return age > max_age_seconds


@dataclass(frozen=True)
class MarginSnapshot:
    """Margin evaluation result."""

    required_margin: Decimal
    available_margin: Decimal
    free_margin: Decimal
    margin_usage_percent: Decimal
    sufficient: bool
    warning: Optional[str] = None


@dataclass(frozen=True)
class CircuitBreakerState:
    """Persistent circuit-breaker state."""

    active: bool = False
    reason: Optional[CircuitBreakerReason] = None
    triggered_at: Optional[datetime] = None
    lockout_until: Optional[datetime] = None
    reset_required: bool = True
    audit_history: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, reason: CircuitBreakerReason, triggered_at: datetime) -> None:
        entry = {
            "reason": reason.value,
            "triggered_at": triggered_at.isoformat(),
        }
        object.__setattr__(self, "audit_history", [*self.audit_history, entry])


@dataclass(frozen=True)
class RiskDecision:
    """Standardized risk decision output."""

    signal_id: str
    symbol: str
    instrument_type: str
    direction: str
    status: RiskDecisionStatus
    rejection_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Position sizing
    volume: Optional[Decimal] = None
    monetary_risk: Optional[Decimal] = None
    risk_percent: Optional[Decimal] = None

    # Stop / target
    stop_loss_price: Optional[Decimal] = None
    stop_distance: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    reward_to_risk: Optional[Decimal] = None

    # Margin / exposure
    estimated_margin: Optional[Decimal] = None
    exposure_before: Optional[PositionExposure] = None
    exposure_after: Optional[PositionExposure] = None

    # Metadata
    account_timestamp: Optional[datetime] = None
    policy_version: Optional[str] = None
    calculation_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    data_source: str = "mock"
    sizing_method: Optional[str] = None
    stop_method: Optional[str] = None
    tp_method: Optional[str] = None

    @property
    def is_approved(self) -> bool:
        return self.status == RiskDecisionStatus.APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.status in (
            RiskDecisionStatus.REJECTED,
            RiskDecisionStatus.LOCKED,
        )


class RiskEngineABC(ABC):
    """Abstract interface for the risk management engine."""

    @abstractmethod
    def evaluate_signal(
        self,
        params: RiskParameters,
        account: AccountSnapshot,
    ) -> RiskDecision:
        """Evaluate a proposed trade signal and return a risk decision."""
        ...

    @abstractmethod
    def validate_policy(self) -> List[str]:
        """Validate the current risk policy. Returns list of errors (empty = valid)."""
        ...

    @abstractmethod
    def is_locked(self) -> bool:
        """Return True if a circuit breaker is active."""
        ...
