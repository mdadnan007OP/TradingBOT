"""Slippage model.

Applies adverse slippage to simulated fills. Adverse means:
    * A BUY (long entry / short exit) fills HIGHER.
    * A SELL (short entry / long exit) fills LOWER.

Slippage is never silently zero unless explicitly configured as NONE.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.backtesting.config import SlippageConfig, SlippageModel as SlippageModelEnum


@dataclass(frozen=True)
class SlippageResult:
    price: Decimal
    """The slipped (actual) fill price."""
    slippage: Decimal
    """Absolute adverse price movement applied (>= 0)."""
    source: str


class SlippageModel:
    """Computes adverse slippage for simulated fills."""

    def __init__(self, config: Optional[SlippageConfig] = None) -> None:
        self.config = config or SlippageConfig()

    def _magnitude(self, symbol: str, price: Decimal) -> Decimal:
        model = self.config.model
        if model == SlippageModelEnum.NONE:
            return Decimal("0")
        if model == SlippageModelEnum.FIXED_POINTS:
            return self.config.fixed_points.get(symbol, Decimal("0"))
        if model == SlippageModelEnum.FRACTION:
            return price * self.config.fraction
        return Decimal("0")

    def apply(self, symbol: str, is_buy: bool, price: Decimal) -> SlippageResult:
        """Apply adverse slippage to a fill of ``price`` for a buy/sell."""
        magnitude = self._magnitude(symbol, price)
        if magnitude <= 0:
            return SlippageResult(price, Decimal("0"), self.config.model.value)
        if is_buy:
            slipped = price + magnitude
        else:
            slipped = price - magnitude
        return SlippageResult(slipped, magnitude, self.config.model.value)