"""Margin and account constraint validation.

Estimates additional margin required for a proposal and checks it against
available/free margin and configured margin-usage limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.risk_management.base import MarginSnapshot
from src.risk_management.config import RiskPolicy


@dataclass(frozen=True)
class MarginResult:
    snapshot: MarginSnapshot
    sufficient: bool
    reasons: list
    warnings: list

    def __post_init__(self):
        if self.reasons is None:
            object.__setattr__(self, "reasons", [])
        if self.warnings is None:
            object.__setattr__(self, "warnings", [])


def estimate_required_margin(
    volume: Decimal,
    price: Decimal,
    contract_size: Optional[Decimal],
    leverage: Optional[Decimal],
    conversion_rate: Decimal = Decimal("1"),
) -> Decimal:
    """Estimate margin required for a position.

    margin = notional / leverage (when leverage known), else notional.
    notional = volume × price × contract_size × conversion_rate.
    """
    if volume <= 0 or price <= 0:
        return Decimal("0")
    notional = volume * price * (contract_size or Decimal("1")) * conversion_rate
    if leverage is not None and leverage > 0:
        return notional / leverage
    return notional


def validate_margin(
    volume: Decimal,
    price: Decimal,
    contract_size: Optional[Decimal],
    account_equity: Decimal,
    account_free_margin: Decimal,
    account_margin_used: Decimal,
    leverage: Optional[Decimal],
    conversion_rate: Decimal = Decimal("1"),
    policy: Optional[RiskPolicy] = None,
) -> MarginResult:
    reasons: list = []
    warnings: list = []

    policy = policy or RiskPolicy()
    required = estimate_required_margin(
        volume, price, contract_size, leverage, conversion_rate
    )

    available = account_free_margin
    margin_level_pct = Decimal("0")
    if account_equity > 0:
        margin_level_pct = (account_free_margin / account_equity) * Decimal("100")

    sufficient = required <= available
    if not sufficient:
        reasons.append(
            f"Required margin {required} exceeds free margin {available}"
        )

    # Margin usage limit: (used + required) / equity <= max
    if account_equity > 0:
        projected_usage = (account_margin_used + required) / account_equity * Decimal("100")
        max_usage = policy.max_margin_usage_percent * Decimal("100")
        if projected_usage > max_usage:
            reasons.append(
                f"Projected margin usage {projected_usage:.2f}% exceeds limit {max_usage:.2f}%"
            )
    else:
        projected_usage = Decimal("0")

    snapshot = MarginSnapshot(
        required_margin=required,
        available_margin=available,
        free_margin=account_free_margin,
        margin_usage_percent=projected_usage,
        sufficient=sufficient and len(reasons) == 0,
        warning=reasons[0] if reasons else None,
    )

    return MarginResult(
        snapshot=snapshot,
        sufficient=sufficient and len(reasons) == 0,
        reasons=reasons,
        warnings=warnings,
    )
