"""Instrument-aware position sizing.

All monetary calculations use Decimal. Volume is rounded DOWN to the broker
lot step; volume is never rounded upward if doing so would exceed the risk
budget. If the calculated volume is below the broker minimum, the proposal is
rejected. Essential instrument specifications are never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional

from src.market_data.models import InstrumentSpec
from src.risk_management.base import (
    RiskDecisionStatus,
    RiskParameters,
    PositionExposure,
    StopMethod,
)
from src.risk_management.config import RiskPolicy, SizingMethod


@dataclass(frozen=True)
class SizingResult:
    volume: Optional[Decimal]
    monetary_risk: Optional[Decimal]
    risk_percent: Optional[Decimal]
    stop_distance: Optional[Decimal]
    risk_per_lot: Optional[Decimal]
    reasons: list = None
    warnings: list = None

    def __post_init__(self):
        if self.reasons is None:
            object.__setattr__(self, "reasons", [])
        if self.warnings is None:
            object.__setattr__(self, "warnings", [])


def round_down_to_step(value: Decimal, step: Decimal) -> Decimal:
    """Round ``value`` down to the nearest multiple of ``step``."""
    if step <= 0:
        return value
    quantized = (value / step).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return quantized * step


def quote_to_account_rate(
    profit_currency: str,
    account_currency: str,
    rates: Dict[str, Decimal],
) -> Optional[Decimal]:
    """Convert 1 unit of ``profit_currency`` to ``account_currency``.

    ``rates`` maps profit_currency -> rate (units of account currency per
    1 unit of profit currency). Returns None when conversion is impossible.
    """
    if profit_currency == account_currency:
        return Decimal("1")
    rate = rates.get(profit_currency)
    if rate is None:
        return None
    if rate <= 0:
        return None
    return rate


def risk_amount_from_policy(
    equity: Decimal,
    balance: Decimal,
    policy: RiskPolicy,
) -> Decimal:
    """Return the monetary risk budget for a single trade."""
    reference = equity if equity > 0 else balance
    if reference <= 0:
        return Decimal("0")
    if policy.sizing_method == SizingMethod.FIXED_MONETARY:
        if policy.fixed_risk_amount is not None:
            return min(policy.fixed_risk_amount, reference)
        return Decimal("0")
    return reference * policy.risk_per_trade_percent


def stop_distance_from_params(
    params: RiskParameters,
    policy: RiskPolicy,
) -> Optional[Decimal]:
    """Derive stop distance in price units from params + policy.

    Priority: explicit stop_loss_price > technical_invalidation >
    atr_based > swing > fixed_distance. Returns None when not determinable.
    """
    entry = params.reference_price
    if entry is None or entry <= 0:
        return None

    method = params.stop_method or policy.default_stop_method

    # Explicit stop-loss price
    if params.stop_loss_price is not None and params.stop_loss_price > 0:
        dist = abs(params.stop_loss_price - entry)
        return dist if dist > 0 else None

    # Technical invalidation (NOT a stop-loss; used as reference only)
    if (
        method == StopMethod.TECHNICAL_INVALIDATION
        and params.technical_invalidation is not None
        and params.technical_invalidation > 0
    ):
        dist = abs(params.technical_invalidation - entry)
        return dist if dist > 0 else None

    # ATR-based
    if method == StopMethod.ATR_BASED:
        if params.atr_value is not None and params.atr_value > 0:
            multiplier = params.atr_multiplier or policy.atr_multiplier
            return params.atr_value * multiplier
        return None

    # Swing structure
    if method == StopMethod.SWING_STRUCTURE:
        if params.direction == "LONG" and params.swing_low is not None:
            dist = entry - params.swing_low
            return dist if dist > 0 else None
        if params.direction == "SHORT" and params.swing_high is not None:
            dist = params.swing_high - entry
            return dist if dist > 0 else None
        return None

    # Fixed distance
    if method == StopMethod.FIXED_DISTANCE:
        if params.stop_distance is not None and params.stop_distance > 0:
            return params.stop_distance
        return None

    return None


def validate_stop_distance(
    stop_distance: Optional[Decimal],
    entry: Optional[Decimal],
    direction: str,
    policy: RiskPolicy,
) -> list:
    reasons = []
    if stop_distance is None:
        reasons.append("Stop distance could not be determined")
        return reasons
    if stop_distance <= 0:
        reasons.append("Stop distance must be positive")
        return reasons
    if policy.min_stop_distance is not None and stop_distance < policy.min_stop_distance:
        reasons.append(
            f"Stop distance {stop_distance} below minimum {policy.min_stop_distance}"
        )
    if policy.max_stop_distance is not None and stop_distance > policy.max_stop_distance:
        reasons.append(
            f"Stop distance {stop_distance} exceeds maximum {policy.max_stop_distance}"
        )
    if (
        policy.max_stop_distance_percent is not None
        and entry is not None
        and entry > 0
    ):
        max_allowed = entry * policy.max_stop_distance_percent
        if stop_distance > max_allowed:
            reasons.append(
                f"Stop distance {stop_distance} exceeds {policy.max_stop_distance_percent * 100}% of entry ({max_allowed})"
            )
    return reasons


class PositionSizer:
    """Calculates instrument-aware position volume and monetary risk."""

    def __init__(
        self,
        spec: InstrumentSpec,
        account_currency: str,
        rates: Optional[Dict[str, Decimal]] = None,
        lot_step: Optional[Decimal] = None,
        min_lot: Optional[Decimal] = None,
        max_lot: Optional[Decimal] = None,
    ) -> None:
        self.spec = spec
        self.account_currency = account_currency
        self.rates = rates or {}
        self.lot_step = lot_step or getattr(spec, "lot_step", None) or Decimal("0.01")
        self.min_lot = min_lot or getattr(spec, "min_lot", None) or Decimal("0.01")
        self.max_lot = max_lot or getattr(spec, "max_lot", None) or Decimal("100.0")

    def _profit_currency(self) -> str:
        """Currency in which profit/loss is realized for this instrument."""
        if self.spec.quote_currency:
            return self.spec.quote_currency
        return self.account_currency

    def _conversion_rate(self) -> Optional[Decimal]:
        return quote_to_account_rate(
            self._profit_currency(), self.account_currency, self.rates
        )

    def size(
        self,
        params: RiskParameters,
        policy: RiskPolicy,
        equity: Decimal,
        balance: Decimal,
    ) -> SizingResult:
        reasons: list = []
        warnings: list = []

        entry = params.reference_price
        if entry is None or entry <= 0:
            return SizingResult(
                None, None, None, None, None,
                reasons=["Reference entry price is missing or invalid"],
                warnings=warnings,
            )

        # 1. Risk budget
        risk_amount = risk_amount_from_policy(equity, balance, policy)
        if risk_amount <= 0:
            return SizingResult(
                None, None, None, None, None,
                reasons=["Risk budget is zero or unavailable (equity/balance missing)"],
                warnings=warnings,
            )

        # 2. Stop distance
        stop_distance = stop_distance_from_params(params, policy)
        if stop_distance is None:
            return SizingResult(
                None, None, None, None, None,
                reasons=["Stop distance could not be determined"],
                warnings=warnings,
            )
        stop_reasons = validate_stop_distance(stop_distance, entry, params.direction, policy)
        reasons.extend(stop_reasons)
        if stop_reasons:
            return SizingResult(
                None, None, None, stop_distance, None,
                reasons=reasons, warnings=warnings,
            )

        # 3. Contract size & conversion
        contract_size = self.spec.contract_size
        if contract_size is None or contract_size <= 0:
            return SizingResult(
                None, None, None, stop_distance, None,
                reasons=["Instrument contract size is missing"],
                warnings=warnings,
            )

        rate = self._conversion_rate()
        if rate is None:
            return SizingResult(
                None, None, None, stop_distance, None,
                reasons=[
                    f"Cannot convert profit currency {self._profit_currency()} "
                    f"to account currency {self.account_currency}"
                ],
                warnings=warnings,
            )

        # 4. Risk per lot (in account currency)
        risk_per_lot = stop_distance * contract_size * rate
        if risk_per_lot <= 0:
            return SizingResult(
                None, None, None, stop_distance, None,
                reasons=["Risk per lot is zero or invalid"],
                warnings=warnings,
            )

        # 5. Raw volume, then round DOWN to lot step
        raw_volume = risk_amount / risk_per_lot
        volume = round_down_to_step(raw_volume, self.lot_step)

        min_lot = self.min_lot
        max_lot = self.max_lot

        if volume < min_lot:
            return SizingResult(
                None, None, None, stop_distance, risk_per_lot,
                reasons=[
                    f"Calculated volume {volume} below broker minimum {min_lot}"
                ],
                warnings=warnings,
            )

        # Cap at max (rounds down, reduces risk — safe)
        if volume > max_lot:
            volume = round_down_to_step(max_lot, lot_step)
            warnings.append(
                f"Volume capped at broker maximum {max_lot}; risk below budget"
            )

        if policy.max_volume is not None and volume > policy.max_volume:
            volume = round_down_to_step(policy.max_volume, lot_step)
            warnings.append(f"Volume capped at policy max_volume {policy.max_volume}")

        if volume < min_lot:
            return SizingResult(
                None, None, None, stop_distance, risk_per_lot,
                reasons=[
                    f"Volume {volume} below broker minimum {min_lot} after caps"
                ],
                warnings=warnings,
            )

        # 6. Monetary risk & risk percent
        monetary_risk = volume * risk_per_lot
        reference = equity if equity > 0 else balance
        risk_percent = (monetary_risk / reference * Decimal("100")) if reference > 0 else None

        return SizingResult(
            volume=volume,
            monetary_risk=monetary_risk,
            risk_percent=risk_percent,
            stop_distance=stop_distance,
            risk_per_lot=risk_per_lot,
            reasons=reasons,
            warnings=warnings,
        )

    def exposure(
        self,
        volume: Decimal,
        price: Decimal,
        direction: str,
    ) -> PositionExposure:
        contract_size = self.spec.contract_size or Decimal("1")
        notional = volume * price * contract_size
        rate = self._conversion_rate() or Decimal("1")
        notional_account = notional * rate
        return PositionExposure(
            symbol=self.spec.canonical_symbol,
            instrument_type=self.spec.instrument_type.value,
            direction=direction,
            volume=volume,
            open_price=price,
            notional=notional_account,
            asset_class=self.spec.instrument_type.value,
        )
