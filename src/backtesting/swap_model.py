"""Swap / overnight financing model.

Computes swap (roll-over) cost for holding a position overnight. Swap is
expressed in price units per lot per night and converted to the account
currency via ``point_value`` (value of 1 price point per lot).

If historical financing data is unavailable, swap is disabled by default and
any enabled swap uses explicitly-configured test assumptions (documented as a
limitation in the report).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from src.backtesting.config import SwapConfig


@dataclass(frozen=True)
class SwapResult:
    amount: Decimal
    """Swap in account currency (positive = cost, negative = credit)."""
    nights: int
    source: str


class SwapModel:
    """Computes overnight swap for simulated positions."""

    def __init__(self, config: Optional[SwapConfig] = None) -> None:
        self.config = config or SwapConfig()

    def _points(self, symbol: str, is_long: bool) -> Decimal:
        table = self.config.long_points if is_long else self.config.short_points
        return table.get(symbol, Decimal("0"))

    def _point_value(self, symbol: str) -> Decimal:
        return self.config.point_value.get(symbol, Decimal("1"))

    def is_triple_night(self, date: datetime) -> bool:
        """Return True if ``date`` is a triple-swap day (default Wednesday)."""
        return date.weekday() in set(self.config.triple_days)

    def swap_for(
        self,
        symbol: str,
        is_long: bool,
        volume: Decimal,
        nights: int,
    ) -> SwapResult:
        """Return swap cost for holding ``volume`` for ``nights`` nights.

        Positive result = cost debited; negative = credit.
        """
        if not self.config.enabled or nights <= 0:
            return SwapResult(Decimal("0"), max(0, nights), "disabled")
        points = self._points(symbol, is_long)
        point_value = self._point_value(symbol)
        total = points * point_value * volume * nights
        return SwapResult(total, nights, "configured")

    def swap_for_period(
        self,
        symbol: str,
        is_long: bool,
        volume: Decimal,
        nights: int,
        night_dates: Optional[list] = None,
    ) -> SwapResult:
        """Swap with triple-night handling given the calendar dates held.

        ``night_dates`` are the dates (midnight boundaries) on which a position
        was held; triple-swap days charge 3x.
        """
        if not self.config.enabled or nights <= 0:
            return SwapResult(Decimal("0"), max(0, nights), "disabled")
        points = self._points(symbol, is_long)
        point_value = self._point_value(symbol)
        total = Decimal("0")
        counted = 0
        for d in night_dates or []:
            mult = Decimal("3") if self.is_triple_night(d) else Decimal("1")
            total += points * point_value * volume * mult
            counted += 1
        if counted == 0:
            # No dates supplied: charge flat nights (no triple handling).
            total = points * point_value * volume * nights
            counted = nights
        return SwapResult(total, counted, "configured")