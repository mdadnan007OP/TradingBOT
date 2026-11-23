"""Aggregating transaction-cost model.

Combines spread, slippage, commission, swap, and currency conversion into a
single, independently-testable facade used by the execution and position
simulators. Each component is also usable on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.backtesting.commission_model import CommissionModel
from src.backtesting.config import ExecutionConfig
from src.backtesting.currency_conversion import CurrencyConverter
from src.backtesting.slippage_model import SlippageModel
from src.backtesting.spread_model import SpreadModel
from src.backtesting.swap_model import SwapModel


@dataclass(frozen=True)
class FillQuote:
    """A resolved executable quote including costs."""

    bid: Decimal
    ask: Decimal
    mid: Decimal
    spread: Decimal
    spread_source: str


class TransactionCostModel:
    """Facade over the individual cost components."""

    def __init__(
        self,
        config: ExecutionConfig,
        converter: Optional[CurrencyConverter] = None,
    ) -> None:
        self.config = config
        self.spread = SpreadModel(config.spread)
        self.slippage = SlippageModel(config.slippage)
        self.commission = CommissionModel(config.commission)
        self.swap = SwapModel(config.swap)
        self.converter = converter or CurrencyConverter()

    def resolve_quote(
        self,
        symbol: str,
        ref_price: Decimal,
        bar=None,
    ) -> FillQuote:
        """Resolve bid/ask and mid for an execution reference price."""
        resolved = self.spread.resolve(symbol, ref_price, bar)
        mid = (resolved.bid + resolved.ask) / 2
        return FillQuote(
            bid=resolved.bid,
            ask=resolved.ask,
            mid=mid,
            spread=resolved.spread,
            spread_source=resolved.source,
        )

    def fill_price(
        self,
        symbol: str,
        is_buy: bool,
        base_price: Decimal,
    ) -> tuple:
        """Apply adverse slippage to ``base_price``.

        Returns (fill_price, slippage_amount).
        """
        result = self.slippage.apply(symbol, is_buy, base_price)
        return result.price, result.slippage

    def commission_round_trip(self, volume: Decimal) -> Decimal:
        return self.commission.entry_and_exit(volume)

    def swap_for(
        self,
        symbol: str,
        is_long: bool,
        volume: Decimal,
        nights: int,
        night_dates=None,
    ) -> Decimal:
        if night_dates is not None:
            return self.swap.swap_for_period(symbol, is_long, volume, nights, night_dates).amount
        return self.swap.swap_for(symbol, is_long, volume, nights).amount

    def to_account(
        self,
        amount_quote: Decimal,
        profit_currency: str,
        timestamp: Optional[datetime] = None,
    ) -> Decimal:
        return self.converter.convert_or(amount_quote, profit_currency, timestamp)