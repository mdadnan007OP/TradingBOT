"""Commission model.

Supports per-lot, per-trade, or no commission. Commission is expressed in the
account currency. Never invents broker fees — values must be configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.backtesting.config import CommissionConfig, CommissionModel as CommissionModelEnum


@dataclass(frozen=True)
class CommissionResult:
    amount: Decimal
    """Commission in account currency (>= 0)."""
    source: str


class CommissionModel:
    """Computes commission for a simulated trade."""

    def __init__(self, config: Optional[CommissionConfig] = None) -> None:
        self.config = config or CommissionConfig()

    def commission_for(self, volume: Decimal) -> CommissionResult:
        model = self.config.model
        if model == CommissionModelEnum.NONE:
            return CommissionResult(Decimal("0"), "none")
        if model == CommissionModelEnum.PER_LOT:
            return CommissionResult(self.config.per_lot * volume, "per_lot")
        if model == CommissionModelEnum.PER_TRADE:
            return CommissionResult(self.config.per_trade, "per_trade")
        return CommissionResult(Decimal("0"), "none")

    def entry_and_exit(self, volume: Decimal) -> Decimal:
        """Total commission for a round-trip (entry + exit).

        For PER_TRADE this is charged once; for PER_LOT it is charged per side.
        """
        model = self.config.model
        if model == CommissionModelEnum.NONE:
            return Decimal("0")
        if model == CommissionModelEnum.PER_TRADE:
            return self.config.per_trade
        if model == CommissionModelEnum.PER_LOT:
            return self.config.per_lot * volume * 2
        return Decimal("0")