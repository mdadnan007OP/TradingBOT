"""Risk policy configuration and validation.

Centralized, configurable risk policies. The engine refuses to approve trades
until the active policy has been explicitly validated. Missing, invalid or
contradictory policies produce a safe rejection/unavailable state.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dataclasses_fields
from datetime import datetime, time, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

from src.risk_management.base import (
    CircuitBreakerReason,
    RiskDecisionStatus,
    SizingMethod,
    StopMethod,
    TakeProfitMethod,
)


class AssetClass(str, Enum):
    FOREX = "forex"
    METAL = "metal"
    ENERGY = "energy"
    INDEX = "index"
    CRYPTO = "crypto"
    EQUITY = "equity"
    OTHER = "other"


@dataclass(frozen=True)
class InstrumentGroup:
    """A group of instruments treated as correlated for exposure purposes."""

    name: str
    symbols: List[str] = field(default_factory=list)
    asset_classes: List[AssetClass] = field(default_factory=list)
    max_correlation: Optional[Decimal] = None
    max_combined_exposure_percent: Optional[Decimal] = None


@dataclass(frozen=True)
class RiskPolicy:
    """Complete risk-management policy.

    All percentages are expressed as fractions (e.g. 0.01 = 1%). Monetary
    values are in the account currency.
    """

    version: str = "1.0.0"
    enabled: bool = True

    # --- Position sizing ---
    sizing_method: SizingMethod = SizingMethod.PERCENT_EQUITY
    risk_per_trade_percent: Decimal = Decimal("0.01")  # 1% of equity
    fixed_risk_amount: Optional[Decimal] = None  # used when FIXED_MONETARY
    min_reward_to_risk: Decimal = Decimal("1.5")
    max_volume: Optional[Decimal] = None

    # --- Stop loss ---
    default_stop_method: StopMethod = StopMethod.TECHNICAL_INVALIDATION
    atr_multiplier: Decimal = Decimal("2.0")
    min_stop_distance: Optional[Decimal] = None
    max_stop_distance: Optional[Decimal] = None
    max_stop_distance_percent: Optional[Decimal] = None  # of entry price

    # --- Take profit ---
    default_tp_method: TakeProfitMethod = TakeProfitMethod.REWARD_TO_RISK
    default_reward_to_risk: Decimal = Decimal("2.0")

    # --- Daily loss ---
    max_daily_loss_percent: Decimal = Decimal("0.05")  # 5% of starting equity
    max_daily_loss_amount: Optional[Decimal] = None
    daily_reset_time: time = time(0, 0, tzinfo=timezone.utc)
    daily_reset_timezone: str = "UTC"

    # --- Drawdown ---
    max_equity_drawdown_percent: Decimal = Decimal("0.10")  # 10%
    max_balance_drawdown_percent: Decimal = Decimal("0.15")  # 15%

    # --- Portfolio ---
    max_positions: int = 5
    max_portfolio_risk_percent: Decimal = Decimal("0.10")  # 10% of equity
    max_exposure_per_instrument_percent: Decimal = Decimal("0.20")  # 20%
    max_exposure_per_asset_class_percent: Decimal = Decimal("0.40")  # 40%
    max_directional_exposure_percent: Optional[Decimal] = None  # e.g. 30% long

    # --- Spread / slippage ---
    max_spread_pips: Optional[Decimal] = None
    max_slippage_estimate: Optional[Decimal] = None

    # --- Consecutive losses ---
    max_consecutive_losses: int = 5

    # --- Margin ---
    max_margin_usage_percent: Decimal = Decimal("0.50")  # 50% of equity

    # --- Cooldown ---
    cooldown_minutes: int = 60
    cooldown_after_rejection: bool = True

    # --- Instrument groups / correlation ---
    instrument_groups: List[InstrumentGroup] = field(default_factory=list)
    correlation_window: int = 100
    min_correlation_data_points: int = 30
    max_correlation_threshold: Optional[Decimal] = Decimal("0.70")

    def validate(self) -> List[str]:
        """Validate policy. Returns list of human-readable errors (empty = valid)."""
        errors: List[str] = []

        if not self.enabled:
            errors.append("Risk policy is disabled")
            return errors

        if self.sizing_method == SizingMethod.PERCENT_EQUITY:
            if not (Decimal("0") < self.risk_per_trade_percent <= Decimal("1")):
                errors.append("risk_per_trade_percent must be in (0, 1]")
        elif self.sizing_method == SizingMethod.FIXED_MONETARY:
            if self.fixed_risk_amount is None or self.fixed_risk_amount <= 0:
                errors.append("fixed_risk_amount must be set and > 0 for FIXED_MONETARY sizing")

        if self.min_reward_to_risk <= 0:
            errors.append("min_reward_to_risk must be > 0")

        if self.max_volume is not None and self.max_volume <= 0:
            errors.append("max_volume must be > 0")

        if self.min_stop_distance is not None and self.min_stop_distance <= 0:
            errors.append("min_stop_distance must be > 0")
        if self.max_stop_distance is not None and self.max_stop_distance <= 0:
            errors.append("max_stop_distance must be > 0")
        if (
            self.min_stop_distance is not None
            and self.max_stop_distance is not None
            and self.min_stop_distance > self.max_stop_distance
        ):
            errors.append("min_stop_distance cannot exceed max_stop_distance")

        if not (Decimal("0") < self.min_reward_to_risk <= Decimal("100")):
            errors.append("min_reward_to_risk must be in (0, 100]")

        if not (Decimal("0") <= self.max_daily_loss_percent <= Decimal("1")):
            errors.append("max_daily_loss_percent must be in [0, 1]")
        if not (Decimal("0") <= self.max_equity_drawdown_percent <= Decimal("1")):
            errors.append("max_equity_drawdown_percent must be in [0, 1]")
        if not (Decimal("0") <= self.max_balance_drawdown_percent <= Decimal("1")):
            errors.append("max_balance_drawdown_percent must be in [0, 1]")

        if self.max_positions < 1:
            errors.append("max_positions must be >= 1")
        if not (Decimal("0") < self.max_portfolio_risk_percent <= Decimal("1")):
            errors.append("max_portfolio_risk_percent must be in (0, 1]")
        if not (Decimal("0") < self.max_exposure_per_instrument_percent <= Decimal("1")):
            errors.append("max_exposure_per_instrument_percent must be in (0, 1]")
        if not (Decimal("0") < self.max_exposure_per_asset_class_percent <= Decimal("1")):
            errors.append("max_exposure_per_asset_class_percent must be in (0, 1]")

        if not (Decimal("0") <= self.max_margin_usage_percent <= Decimal("1")):
            errors.append("max_margin_usage_percent must be in [0, 1]")

        if self.max_consecutive_losses < 1:
            errors.append("max_consecutive_losses must be >= 1")
        if self.cooldown_minutes < 0:
            errors.append("cooldown_minutes must be >= 0")

        if self.max_correlation_threshold is not None:
            if not (Decimal("0") < self.max_correlation_threshold <= Decimal("1")):
                errors.append("max_correlation_threshold must be in (0, 1]")
        if self.correlation_window < 1:
            errors.append("correlation_window must be >= 1")
        if self.min_correlation_data_points < 1:
            errors.append("min_correlation_data_points must be >= 1")

        for group in self.instrument_groups:
            if not group.symbols:
                errors.append(f"Instrument group '{group.name}' has no symbols")

        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0


@dataclass(frozen=True)
class RiskConfig:
    """Runtime risk configuration wrapper.

    Wraps a RiskPolicy and tracks validation state. The engine must not approve
    trades when the policy is invalid.
    """

    policy: RiskPolicy
    validated: bool = False
    validation_errors: List[str] = field(default_factory=list)
    validated_at: Optional[datetime] = None

    @property
    def is_valid(self) -> bool:
        return self.validated and len(self.validation_errors) == 0 and self.policy.is_valid()

    def validate_policy(self) -> "RiskConfig":
        errors = self.policy.validate()
        return RiskConfig(
            policy=self.policy,
            validated=len(errors) == 0,
            validation_errors=errors,
            validated_at=datetime.now(timezone.utc) if len(errors) == 0 else None,
        )


def test_policy(overrides: Optional[Dict[str, object]] = None) -> RiskPolicy:
    """Build a deterministic policy for automated testing.

    Args:
        overrides: Field overrides applied to the default test policy.
    """
    base = RiskPolicy(
        version="test-1.0.0",
        enabled=True,
        sizing_method=SizingMethod.PERCENT_EQUITY,
        risk_per_trade_percent=Decimal("0.01"),
        fixed_risk_amount=None,
        min_reward_to_risk=Decimal("1.5"),
        max_volume=Decimal("100.0"),
        default_stop_method=StopMethod.TECHNICAL_INVALIDATION,
        atr_multiplier=Decimal("2.0"),
        min_stop_distance=Decimal("0.0001"),
        max_stop_distance=Decimal("5.0"),
        max_stop_distance_percent=Decimal("0.10"),
        default_tp_method=TakeProfitMethod.REWARD_TO_RISK,
        default_reward_to_risk=Decimal("2.0"),
        max_daily_loss_percent=Decimal("0.05"),
        max_daily_loss_amount=None,
        daily_reset_time=time(0, 0, tzinfo=timezone.utc),
        daily_reset_timezone="UTC",
        max_equity_drawdown_percent=Decimal("0.10"),
        max_balance_drawdown_percent=Decimal("0.15"),
        max_positions=5,
        max_portfolio_risk_percent=Decimal("0.10"),
        max_exposure_per_instrument_percent=Decimal("0.20"),
        max_exposure_per_asset_class_percent=Decimal("0.40"),
        max_directional_exposure_percent=None,
        max_spread_pips=None,
        max_slippage_estimate=None,
        max_consecutive_losses=5,
        max_margin_usage_percent=Decimal("0.50"),
        cooldown_minutes=60,
        cooldown_after_rejection=True,
        instrument_groups=[
            InstrumentGroup(
                name="majors",
                symbols=["EURUSD", "GBPUSD", "USDCHF", "USDCAD"],
                asset_classes=[AssetClass.FOREX],
                max_correlation=Decimal("0.70"),
                max_combined_exposure_percent=Decimal("0.40"),
            ),
            InstrumentGroup(
                name="precious_metals",
                symbols=["XAUUSD", "XAGUSD"],
                asset_classes=[AssetClass.METAL],
                max_correlation=Decimal("0.70"),
                max_combined_exposure_percent=Decimal("0.30"),
            ),
        ],
        correlation_window=100,
        min_correlation_data_points=30,
        max_correlation_threshold=Decimal("0.70"),
    )
    if not overrides:
        return base
    fields = {f.name for f in dataclasses_fields(RiskPolicy)}
    applied: Dict[str, object] = {f.name: getattr(base, f.name) for f in dataclasses_fields(RiskPolicy)}
    for key, value in overrides.items():
        if key not in fields:
            raise ValueError(f"Unknown policy field: {key}")
        applied[key] = value
    return RiskPolicy(**applied)
