"""Spread model.

Resolves bid/ask for a simulated bar using, in priority order:
    1. Bar bid/ask fields (if present and config allows).
    2. Bar ``spread`` field (split around a reference price).
    3. Configured fixed spread per instrument.
    4. Configured fractional spread.

A spread is NEVER silently assumed to be zero: when no source is available the
resolved source is ``"none"`` and the caller is expected to surface a warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.backtesting.config import SpreadConfig
from src.market_data.models import OHLCBar


@dataclass(frozen=True)
class ResolvedQuote:
    """A resolved (bid, ask) quote with provenance."""

    bid: Decimal
    ask: Decimal
    spread: Decimal
    source: str


class SpreadModel:
    """Resolves bid/ask quotes for simulated bars."""

    def __init__(self, config: Optional[SpreadConfig] = None) -> None:
        self.config = config or SpreadConfig()

    def resolve(
        self,
        symbol: str,
        ref_price: Decimal,
        bar: Optional[OHLCBar] = None,
    ) -> ResolvedQuote:
        """Return a ResolvedQuote for ``symbol`` at ``ref_price``."""
        if bar is not None and self.config.use_bar_bid_ask and bar.bid is not None and bar.ask is not None:
            return ResolvedQuote(bar.bid, bar.ask, bar.ask - bar.bid, "bid_ask")

        if bar is not None and self.config.use_bar_spread_field and bar.spread is not None:
            half = bar.spread / 2
            return ResolvedQuote(ref_price - half, ref_price + half, bar.spread, "bar_spread")

        fixed = self.config.fixed_spread.get(symbol)
        if fixed is not None:
            half = fixed / 2
            return ResolvedQuote(ref_price - half, ref_price + half, fixed, "fixed")

        if self.config.fractional_spread > 0:
            spread = ref_price * self.config.fractional_spread
            half = spread / 2
            return ResolvedQuote(ref_price - half, ref_price + half, spread, "fractional")

        # No spread information available — do NOT pretend it is zero silently.
        return ResolvedQuote(ref_price, ref_price, Decimal("0"), "none")

    def half_spread(self, symbol: str, ref_price: Decimal, bar: Optional[OHLCBar] = None) -> Decimal:
        """Return half the spread (adverse cost per side)."""
        return self.resolve(symbol, ref_price, bar).spread / 2