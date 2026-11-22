"""Portfolio exposure limit evaluation.

Checks proposed and current exposure against configured limits:
max positions, max portfolio risk, per-instrument, per-asset-class, and
directional exposure.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from src.risk_management.config import RiskPolicy
from src.risk_management.exposure import ExposureSummary
from src.risk_management.models import PositionExposure


@dataclass(frozen=True)
class PortfolioRiskResult:
    within_limits: bool
    reasons: List[str]
    warnings: List[str]
    max_positions_ok: bool
    portfolio_risk_ok: bool
    instrument_exposure_ok: bool
    asset_class_exposure_ok: bool
    directional_exposure_ok: bool


def evaluate_portfolio_risk(
    summary: ExposureSummary,
    proposed_volume: Decimal,
    proposed_notional: Decimal,
    proposed_direction: str,
    proposed_symbol: str,
    proposed_asset_class: str,
    equity: Decimal,
    policy: RiskPolicy,
    current_portfolio_risk_percent: Optional[Decimal] = None,
) -> PortfolioRiskResult:
    reasons: List[str] = []
    warnings: List[str] = []

    # 1. Max positions
    max_positions_ok = summary.total_positions < policy.max_positions
    if not max_positions_ok:
        reasons.append(
            f"Maximum positions reached ({summary.total_positions} >= {policy.max_positions})"
        )

    # 2. Portfolio risk
    proposed_risk_percent = Decimal("0")
    if equity > 0 and current_portfolio_risk_percent is not None:
        proposed_risk_percent = current_portfolio_risk_percent
    portfolio_risk_ok = (
        proposed_risk_percent <= policy.max_portfolio_risk_percent
    )
    if not portfolio_risk_ok:
        reasons.append(
            f"Portfolio risk {proposed_risk_percent:.4f}% exceeds limit "
            f"{policy.max_portfolio_risk_percent}%"
        )

    # 3. Per-instrument exposure
    instrument_exposure_ok = True
    inst_limit = equity * policy.max_exposure_per_instrument_percent if equity > 0 else None
    existing_inst = summary.by_instrument.get(proposed_symbol, None)
    inst_notional_after = Decimal("0")
    if existing_inst is not None:
        inst_notional_after = existing_inst.notional + proposed_notional
    else:
        inst_notional_after = proposed_notional
    if inst_limit is not None and inst_notional_after > inst_limit:
        instrument_exposure_ok = False
        reasons.append(
            f"Instrument exposure for {proposed_symbol} "
            f"({inst_notional_after}) exceeds limit ({inst_limit})"
        )

    # 4. Per-asset-class exposure
    asset_class_exposure_ok = True
    ac_limit = equity * policy.max_exposure_per_asset_class_percent if equity > 0 else None
    existing_ac = summary.by_asset_class.get(proposed_asset_class, Decimal("0"))
    ac_notional_after = existing_ac + proposed_notional
    if ac_limit is not None and ac_notional_after > ac_limit:
        asset_class_exposure_ok = False
        reasons.append(
            f"Asset-class exposure for {proposed_asset_class} "
            f"({ac_notional_after}) exceeds limit ({ac_limit})"
        )

    # 5. Directional exposure
    directional_exposure_ok = True
    if policy.max_directional_exposure_percent is not None and equity > 0:
        dir_limit = equity * policy.max_directional_exposure_percent
        if proposed_direction == "LONG":
            dir_after = summary.long_exposure + proposed_notional
        else:
            dir_after = summary.short_exposure + proposed_notional
        if dir_after > dir_limit:
            directional_exposure_ok = False
            reasons.append(
                f"{proposed_direction} directional exposure {dir_after} "
                f"exceeds limit {dir_limit}"
            )

    within_limits = (
        max_positions_ok
        and portfolio_risk_ok
        and instrument_exposure_ok
        and asset_class_exposure_ok
        and directional_exposure_ok
    )

    return PortfolioRiskResult(
        within_limits=within_limits,
        reasons=reasons,
        warnings=warnings,
        max_positions_ok=max_positions_ok,
        portfolio_risk_ok=portfolio_risk_ok,
        instrument_exposure_ok=instrument_exposure_ok,
        asset_class_exposure_ok=asset_class_exposure_ok,
        directional_exposure_ok=directional_exposure_ok,
    )
