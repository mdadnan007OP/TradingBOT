"""Take-profit validation and calculation.

Validates take-profit prices against entry and stop distance, enforces the
minimum reward-to-risk ratio, and derives targets from R:R, ATR, technical
levels, or support/resistance.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from src.risk_management.base import (
    RiskParameters,
    TakeProfitMethod,
)
from src.risk_management.config import RiskPolicy


@dataclass(frozen=True)
class TakeProfitResult:
    take_profit_price: Optional[Decimal]
    target_distance: Optional[Decimal]
    reward_to_risk: Optional[Decimal]
    method: Optional[str]
    valid: bool
    reasons: List[str]
    warnings: List[str]


def _validate_tp_side(
    entry: Decimal,
    tp_price: Decimal,
    direction: str,
) -> List[str]:
    reasons: List[str] = []
    if direction == "LONG":
        if tp_price <= entry:
            reasons.append(
                f"LONG take-profit {tp_price} must be above entry {entry}"
            )
    elif direction == "SHORT":
        if tp_price >= entry:
            reasons.append(
                f"SHORT take-profit {tp_price} must be below entry {entry}"
            )
    return reasons


def calculate_tp_price(
    entry: Decimal,
    target_distance: Decimal,
    direction: str,
) -> Decimal:
    """Return the take-profit price for a given entry and target distance."""
    if direction == "LONG":
        return entry + target_distance
    if direction == "SHORT":
        return entry - target_distance
    raise ValueError(f"Unsupported direction: {direction}")


def validate_take_profit_price(
    entry: Decimal,
    stop_distance: Decimal,
    tp_price: Decimal,
    direction: str,
    policy: RiskPolicy,
) -> TakeProfitResult:
    reasons: List[str] = []
    warnings: List[str] = []

    if tp_price is None or tp_price <= 0:
        return TakeProfitResult(
            None, None, None, None, False,
            reasons=["Take-profit price is missing or invalid"],
            warnings=warnings,
        )

    side_reasons = _validate_tp_side(entry, tp_price, direction)
    reasons.extend(side_reasons)

    target_distance = abs(entry - tp_price)
    if target_distance <= 0:
        return TakeProfitResult(
            tp_price, Decimal("0"), None, None, False,
            reasons=["Target distance must be positive"] + reasons,
            warnings=warnings,
        )

    if stop_distance <= 0:
        return TakeProfitResult(
            tp_price, target_distance, None, None, False,
            reasons=["Stop distance must be positive to compute R:R"],
            warnings=warnings,
        )

    rr = target_distance / stop_distance
    min_rr = policy.min_reward_to_risk
    if rr < min_rr:
        reasons.append(
            f"Reward-to-risk {rr:.4f} below minimum {min_rr}"
        )

    return TakeProfitResult(
        take_profit_price=tp_price,
        target_distance=target_distance,
        reward_to_risk=rr,
        method="explicit",
        valid=len(reasons) == 0,
        reasons=reasons,
        warnings=warnings,
    )


def derive_target_distance(
    params: RiskParameters,
    stop_distance: Decimal,
    policy: RiskPolicy,
) -> Optional[Decimal]:
    """Derive take-profit target distance from params + policy."""
    method = params.tp_method or policy.default_tp_method
    entry = params.reference_price
    if entry is None or entry <= 0:
        return None

    if method == TakeProfitMethod.REWARD_TO_RISK:
        rr = params.reward_to_risk or policy.default_reward_to_risk
        if rr is None or rr <= 0:
            return None
        return stop_distance * rr

    if method == TakeProfitMethod.ATR_BASED:
        if params.atr_value is not None and params.atr_value > 0:
            multiplier = params.atr_multiplier or policy.atr_multiplier
            return params.atr_value * multiplier
        return None

    if method == TakeProfitMethod.TECHNICAL_TARGET:
        if params.direction == "LONG" and params.take_profit_price is not None:
            return params.take_profit_price - entry
        if params.direction == "SHORT" and params.take_profit_price is not None:
            return entry - params.take_profit_price
        return None

    if method == TakeProfitMethod.SUPPORT_RESISTANCE:
        # Same as technical target for now; callers can pass a level.
        if params.take_profit_price is not None:
            return abs(params.take_profit_price - entry)
        return None

    return None
