"""Risk Management Engine (Phase 6).

Centralized, execution-independent risk evaluation for proposed trade signals.
Calculates position sizing, validates stop-loss/take-profit, enforces account
and portfolio protections, and produces structured risk decisions.

Does NOT place, modify or close orders. A RISK_APPROVED decision is hypothetical
and does not authorize execution.
"""

from __future__ import annotations

from src.risk_management.base import (
    AccountSnapshot,
    CircuitBreakerReason,
    CircuitBreakerState,
    MarginSnapshot,
    PositionExposure,
    RiskDecision,
    RiskDecisionStatus,
    RiskEngineABC,
    RiskParameters,
    SizingMethod,
    StopMethod,
    TakeProfitMethod,
)
from src.risk_management.config import (
    AssetClass,
    InstrumentGroup,
    RiskConfig,
    RiskPolicy,
    test_policy,
)
from src.risk_management.models import (
    DailyPnLState,
    DrawdownState,
    ExposureSummary,
    RiskReport,
)

__version__ = "0.6.0"
__all__ = [
    "AccountSnapshot",
    "AssetClass",
    "CircuitBreakerReason",
    "CircuitBreakerState",
    "DailyPnLState",
    "DrawdownState",
    "ExposureSummary",
    "InstrumentGroup",
    "MarginSnapshot",
    "PositionExposure",
    "RiskConfig",
    "RiskDecision",
    "RiskDecisionStatus",
    "RiskEngineABC",
    "RiskParameters",
    "RiskPolicy",
    "RiskReport",
    "SizingMethod",
    "StopMethod",
    "TakeProfitMethod",
    "test_policy",
]
