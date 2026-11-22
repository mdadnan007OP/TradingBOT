"""Stop-loss validation and calculation.

Validates proposed stop-loss prices and derives stop-loss references from
technical invalidation, ATR, swing structure, or fixed distance. Never moves
a technical invalidation level silently to force an acceptable size.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from src.risk_management.base import (
    RiskDecisionStatus,
    RiskParameters,
    StopMethod,
)
from src.risk_management.config import RiskPolicy


@dataclass(frozen=True)
class StopLossResult:
    stop_loss_price: Optional[Decimal]
    stop_distance: Optional[Decimal]
    method: Optional[str]
    valid: bool
    reasons: List[str]
    warnings: List[str]
    risk_exceeds_budget: bool = False


def _validate_side(
    entry: Decimal,
    stop_price: Decimal,
    direction: str,
) -> List[str]:
    reasons: List[str] = []
    if direction == "LONG":
        if stop_price >= entry:
            reasons.append(
                f"LONG stop-loss {stop_price} must be below entry {entry}"
            )
    elif direction == "SHORT":
        if stop_price <= entry:
            reasons.append(
                f"SHORT stop-loss {stop_price} must be above entry {entry}"
            )
    return reasons


def calculate_stop_price(
    entry: Decimal,
    stop_distance: Decimal,
    direction: str,
) -> Decimal:
    """Return the stop-loss price for a given entry and distance."""
    if direction == "LONG":
        return entry - stop_distance
    if direction == "SHORT":
        return entry + stop_distance
    raise ValueError(f"Unsupported direction: {direction}")


def validate_stop_loss_price(
    entry: Decimal,
    stop_price: Decimal,
    direction: str,
    policy: RiskPolicy,
) -> StopLossResult:
    reasons: List[str] = []
    warnings: List[str] = []

    if stop_price is None or stop_price <= 0:
        return StopLossResult(
            None, None, None, False,
            reasons=["Stop-loss price is missing or invalid"],
            warnings=warnings,
        )

    side_reasons = _validate_side(entry, stop_price, direction)
    reasons.extend(side_reasons)

    distance = abs(entry - stop_price)
    if distance <= 0:
        return StopLossResult(
            stop_price, Decimal("0"), None, False,
            reasons=["Stop distance must be positive"] + reasons,
            warnings=warnings,
        )

    limit_reasons = _validate_distance_limits(distance, entry, policy)
    reasons.extend(limit_reasons)

    return StopLossResult(
        stop_loss_price=stop_price,
        stop_distance=distance,
        method="explicit",
        valid=len(reasons) == 0,
        reasons=reasons,
        warnings=warnings,
    )


def _validate_distance_limits(
    distance: Decimal,
    entry: Decimal,
    policy: RiskPolicy,
) -> List[str]:
    reasons: List[str] = []
    if policy.min_stop_distance is not None and distance < policy.min_stop_distance:
        reasons.append(
            f"Stop distance {distance} below minimum {policy.min_stop_distance}"
        )
    if policy.max_stop_distance is not None and distance > policy.max_stop_distance:
        reasons.append(
            f"Stop distance {distance} exceeds maximum {policy.max_stop_distance}"
        )
    if (
        policy.max_stop_distance_percent is not None
        and entry > 0
    ):
        max_allowed = entry * policy.max_stop_distance_percent
        if distance > max_allowed:
            reasons.append(
                f"Stop distance {distance} exceeds "
                f"{policy.max_stop_distance_percent * 100}% of entry ({max_allowed})"
            )
    return reasons


def derive_stop_distance(
    params: RiskParameters,
    policy: RiskPolicy,
) -> Optional[Decimal]:
    """Derive stop distance from params + policy without side validation."""
    from src.risk_management.position_sizing import stop_distance_from_params

    return stop_distance_from_params(params, policy)


def check_stop_against_budget(
    stop_distance: Decimal,
    entry: Decimal,
    direction: str,
    volume: Decimal,
    contract_size: Decimal,
    conversion_rate: Decimal,
    risk_budget: Decimal,
) -> bool:
    """Return True if the stop-loss risk stays within the budget."""
    if volume <= 0 or contract_size <= 0 or conversion_rate <= 0:
        return False
    risk = volume * stop_distance * contract_size * conversion_rate
    return risk <= risk_budget
