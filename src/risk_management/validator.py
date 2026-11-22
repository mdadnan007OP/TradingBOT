"""Signal, account, and instrument pre-validation for risk evaluation.

All checks are read-only and produce explicit reasons. Missing essential
information results in REQUIRES_INFORMATION, never a silent approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from src.market_data.models import InstrumentSpec, DataSource
from src.risk_management.base import (
    AccountSnapshot,
    RiskDecisionStatus,
    RiskParameters,
)
from src.risk_management.config import RiskPolicy


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    status: RiskDecisionStatus
    reasons: List[str]
    missing_fields: List[str] = None

    def __post_init__(self):
        if self.missing_fields is None:
            object.__setattr__(self, "missing_fields", [])


def validate_signal_params(
    params: RiskParameters,
) -> ValidationResult:
    reasons: List[str] = []
    missing: List[str] = []

    if not params.signal_id:
        reasons.append("Signal ID is missing")
    if not params.symbol:
        reasons.append("Symbol is missing")
        missing.append("symbol")
    if not params.direction or params.direction not in ("LONG", "SHORT"):
        reasons.append(f"Invalid direction: {params.direction}")
    if params.reference_price is None or params.reference_price <= 0:
        reasons.append("Reference entry price is missing or invalid")
        missing.append("reference_price")

    status = (
        RiskDecisionStatus.REQUIRES_INFORMATION
        if missing
        else RiskDecisionStatus.REJECTED
    ) if reasons else RiskDecisionStatus.APPROVED

    return ValidationResult(
        valid=len(reasons) == 0,
        status=status,
        reasons=reasons,
        missing_fields=missing,
    )


def validate_account(
    account: AccountSnapshot,
    max_staleness_seconds: int,
) -> ValidationResult:
    reasons: List[str] = []
    missing: List[str] = []

    if account.balance <= 0:
        reasons.append("Account balance is missing or zero")
        missing.append("balance")
    if account.equity <= 0:
        reasons.append("Account equity is missing or zero")
        missing.append("equity")
    if not account.currency:
        reasons.append("Account currency is missing")
        missing.append("currency")
    if account.is_stale(max_staleness_seconds):
        reasons.append("Account snapshot is stale")
        missing.append("account_timestamp")

    status = (
        RiskDecisionStatus.REQUIRES_INFORMATION
        if missing
        else (RiskDecisionStatus.REJECTED if reasons else RiskDecisionStatus.APPROVED)
    )
    return ValidationResult(
        valid=len(reasons) == 0,
        status=status,
        reasons=reasons,
        missing_fields=missing,
    )


def validate_instrument_spec(
    symbol: str,
    spec: Optional[InstrumentSpec],
) -> ValidationResult:
    reasons: List[str] = []
    missing: List[str] = []

    if spec is None:
        reasons.append(f"No instrument specification for {symbol}")
        missing.append("instrument_spec")
        return ValidationResult(
            valid=False,
            status=RiskDecisionStatus.REQUIRES_INFORMATION,
            reasons=reasons,
            missing_fields=missing,
        )

    if spec.contract_size is None or spec.contract_size <= 0:
        reasons.append(f"Contract size missing for {symbol}")
        missing.append("contract_size")
    # lot_step / min_lot / max_lot are optional: PositionSizer applies defaults
    # when the InstrumentSpec does not carry them (avoid duplicating spec model).

    status = (
        RiskDecisionStatus.REQUIRES_INFORMATION
        if missing
        else (RiskDecisionStatus.REJECTED if reasons else RiskDecisionStatus.APPROVED)
    )
    return ValidationResult(
        valid=len(reasons) == 0,
        status=status,
        reasons=reasons,
        missing_fields=missing,
    )


def validate_policy(policy: RiskPolicy) -> List[str]:
    """Validate a risk policy. Returns a list of errors (empty = valid)."""
    return policy.validate()
