"""Risk management data models.

Immutable frozen dataclasses for exposures, margin, drawdown state and reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.risk_management.base import (
    AccountSnapshot,
    CircuitBreakerReason,
    CircuitBreakerState,
    PositionExposure,
    RiskDecision,
    RiskParameters,
)


@dataclass(frozen=True)
class DrawdownState:
    """Persistent drawdown tracking state.

    High-watermark is persisted so an application restart cannot accidentally
    reset protection limits.
    """

    equity_high_watermark: Decimal
    balance_high_watermark: Decimal
    current_equity_drawdown: Decimal = Decimal("0")
    current_balance_drawdown: Decimal = Decimal("0")
    max_equity_drawdown_ever: Decimal = Decimal("0")
    max_balance_drawdown_ever: Decimal = Decimal("0")
    updated_at: Optional[datetime] = None

    def compute_equity_drawdown(self, equity: Decimal) -> Decimal:
        if self.equity_high_watermark <= 0:
            return Decimal("0")
        dd = self.equity_high_watermark - equity
        if dd < 0:
            return Decimal("0")
        return dd / self.equity_high_watermark * Decimal("100")

    def compute_balance_drawdown(self, balance: Decimal) -> Decimal:
        if self.balance_high_watermark <= 0:
            return Decimal("0")
        dd = self.balance_high_watermark - balance
        if dd < 0:
            return Decimal("0")
        return dd / self.balance_high_watermark * Decimal("100")


@dataclass(frozen=True)
class DailyPnLState:
    """Daily profit/loss tracking state.

    Deposits and withdrawals adjust the starting reference so they are not
    mistaken for trading profit or loss.
    """

    starting_balance: Decimal
    starting_equity: Decimal
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    deposits: Decimal = Decimal("0")
    withdrawals: Decimal = Decimal("0")
    date: Optional[str] = None
    trading_locked: bool = False
    locked_at: Optional[datetime] = None

    @property
    def net_daily_pnl(self) -> Decimal:
        return self.realized_pnl + self.unrealized_pnl

    @property
    def net_daily_pnl_percent(self) -> Decimal:
        reference = self.starting_equity if self.starting_equity > 0 else self.starting_balance
        if reference <= 0:
            return Decimal("0")
        return self.net_daily_pnl / reference * Decimal("100")

    @property
    def adjusted_starting_reference(self) -> Decimal:
        """Starting reference adjusted for deposits/withdrawals.

        Deposits increase the reference (they are not profit); withdrawals
        decrease it (they are not loss).
        """
        return self.starting_balance + self.deposits - self.withdrawals


@dataclass(frozen=True)
class ExposureSummary:
    """Aggregated portfolio exposure."""

    total_positions: int
    total_notional: Decimal
    total_risk: Decimal
    long_exposure: Decimal
    short_exposure: Decimal
    by_instrument: Dict[str, PositionExposure] = field(default_factory=dict)
    by_asset_class: Dict[str, Decimal] = field(default_factory=dict)
    directional_bias: str = "neutral"  # long | short | neutral


@dataclass(frozen=True)
class CorrelationResult:
    """Correlation evaluation result for a candidate symbol against open positions."""

    candidate_symbol: str
    correlated_symbols: List[str] = field(default_factory=list)
    max_correlation: Optional[Decimal] = None
    average_correlation: Optional[Decimal] = None
    window_used: Optional[int] = None
    data_points: int = 0
    sufficient_data: bool = False
    breach: bool = False
    reason: Optional[str] = None


@dataclass(frozen=True)
class RiskReport:
    """Complete structured risk report for a decision."""

    decision: RiskDecision
    account_snapshot: AccountSnapshot
    drawdown_state: DrawdownState
    daily_pnl_state: DailyPnLState
    exposure_summary: ExposureSummary
    correlation: CorrelationResult
    margin: Any  # MarginSnapshot
    circuit_breaker: CircuitBreakerState
    policy_version: Optional[str] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": {
                "signal_id": self.decision.signal_id,
                "symbol": self.decision.symbol,
                "instrument_type": self.decision.instrument_type,
                "direction": self.decision.direction,
                "status": self.decision.status.value,
                "rejection_reasons": self.decision.rejection_reasons,
                "warnings": self.decision.warnings,
                "volume": str(self.decision.volume) if self.decision.volume is not None else None,
                "monetary_risk": str(self.decision.monetary_risk) if self.decision.monetary_risk is not None else None,
                "risk_percent": str(self.decision.risk_percent) if self.decision.risk_percent is not None else None,
                "stop_loss_price": str(self.decision.stop_loss_price) if self.decision.stop_loss_price is not None else None,
                "take_profit_price": str(self.decision.take_profit_price) if self.decision.take_profit_price is not None else None,
                "reward_to_risk": str(self.decision.reward_to_risk) if self.decision.reward_to_risk is not None else None,
                "estimated_margin": str(self.decision.estimated_margin) if self.decision.estimated_margin is not None else None,
                "calculation_timestamp": self.decision.calculation_timestamp.isoformat(),
                "data_source": self.decision.data_source,
            },
            "account": {
                "login": self.account_snapshot.login,
                "currency": self.account_snapshot.currency,
                "balance": str(self.account_snapshot.balance),
                "equity": str(self.account_snapshot.equity),
                "free_margin": str(self.account_snapshot.free_margin),
                "trade_mode": self.account_snapshot.trade_mode,
                "timestamp": (
                    self.account_snapshot.timestamp.isoformat()
                    if self.account_snapshot.timestamp else None
                ),
            },
            "policy_version": self.policy_version,
            "generated_at": self.generated_at.isoformat(),
        }
