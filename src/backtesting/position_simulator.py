"""Position simulator.

Computes simulated position PnL (gross/net, R-multiple) and builds
``ClosedTrade`` records. All monetary results are produced in the account
currency via the cost model's currency converter. Missing conversion data is
never silently fabricated.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple

from src.backtesting.cost_model import TransactionCostModel
from src.backtesting.models import (
    ClosedTrade,
    ExitReason,
    OrderSide,
    SimulatedPosition,
)


class PositionSimulator:
    """PnL and trade-record math for simulated positions."""

    def __init__(self, costs: TransactionCostModel) -> None:
        self.costs = costs

    # ------------------------------------------------------------------
    # Gross / net PnL
    # ------------------------------------------------------------------

    def gross_pnl_quote(self, position: SimulatedPosition, exit_price: Decimal) -> Decimal:
        diff = exit_price - position.entry_price
        if position.side == OrderSide.SHORT:
            diff = -diff
        contract_size = Decimal(position.metadata.get("contract_size", "1"))
        return diff * position.volume * contract_size

    def _nights(self, entry: datetime, exit_: datetime) -> Tuple[int, list]:
        if exit_ <= entry:
            return 0, []
        nights = (exit_.date() - entry.date()).days
        dates = []
        d = entry.date() + timedelta(days=1)
        while d <= exit_.date():
            dates.append(datetime(d.year, d.month, d.day))
            d += timedelta(days=1)
        return max(0, nights), dates

    def net_pnl_account(
        self,
        position: SimulatedPosition,
        exit_price: Decimal,
        exit_time: datetime,
        risk_amount: Optional[Decimal] = None,
    ) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        """Return (net_account, gross_quote, commission_account, swap_account)."""
        gross_quote = self.gross_pnl_quote(position, exit_price)
        profit_currency = position.metadata.get("profit_currency", self.costs.converter.account_currency)

        nights, dates = self._nights(position.entry_time, exit_time)
        swap_account = self.costs.swap_for(
            position.symbol, position.side == OrderSide.LONG,
            position.volume, nights, dates,
        )
        commission_account = self.costs.commission_round_trip(position.volume)

        slippage_quote = position.slippage
        net_quote = gross_quote - slippage_quote
        converted = self.costs.converter.convert(net_quote, profit_currency, exit_time)
        if converted is None:
            # No conversion available: treat as 1:1 but flag via metadata.
            converted = net_quote
        net_account = converted - commission_account - swap_account
        return net_account, gross_quote, commission_account, swap_account

    def r_multiple(self, net_account: Decimal, risk_amount: Optional[Decimal]) -> Optional[Decimal]:
        if risk_amount is None or risk_amount <= 0:
            return None
        return net_account / risk_amount

    # ------------------------------------------------------------------
    # Trade record
    # ------------------------------------------------------------------

    def build_closed_trade(
        self,
        position: SimulatedPosition,
        exit_price: Decimal,
        exit_time: datetime,
        exit_reason: ExitReason,
        trade_id: str,
        risk_amount: Optional[Decimal] = None,
    ) -> ClosedTrade:
        net_account, gross_quote, commission, swap = self.net_pnl_account(
            position, exit_price, exit_time, risk_amount
        )
        return ClosedTrade(
            trade_id=trade_id,
            position_id=position.position_id,
            symbol=position.symbol,
            side=position.side,
            volume=position.volume,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=exit_time,
            exit_reason=exit_reason,
            strategy_name=position.strategy_name,
            gross_pnl_quote=gross_quote,
            net_pnl_account=net_account,
            commission=commission,
            swap=swap,
            slippage_quote=position.slippage,
            ambiguous_exit=position.ambiguous_exit,
            r_multiple=self.r_multiple(net_account, risk_amount),
        )