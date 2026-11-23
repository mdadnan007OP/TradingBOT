"""Portfolio / account simulator.

Central simulated account: balance, equity, margin, open positions, closed
trades, commissions, swaps and costs. Supports hedging and (simplified)
netting. All state is internal to the simulation — nothing is sent to a broker.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from src.backtesting.config import AccountConfig
from src.backtesting.cost_model import TransactionCostModel
from src.backtesting.execution_simulator import ExecutionSimulator
from src.backtesting.models import (
    ClosedTrade,
    EquityPoint,
    ExitReason,
    OrderSide,
    PositionStatus,
    SimulatedPosition,
)
from src.backtesting.order_simulator import OrderSimulator
from src.backtesting.position_simulator import PositionSimulator
from src.market_data.models import InstrumentSpec
from src.market_data.models import OHLCBar
from src.risk_management.base import AccountSnapshot


class PortfolioSimulator:
    """Simulated trading account and portfolio."""

    def __init__(
        self,
        account_config: AccountConfig,
        costs: TransactionCostModel,
        execution: ExecutionSimulator,
        specs: Optional[Dict[str, InstrumentSpec]] = None,
    ) -> None:
        self.account = account_config
        self.currency = account_config.currency
        self.leverage = account_config.leverage
        self.position_mode = account_config.position_mode
        self.balance: Decimal = account_config.starting_balance
        self.costs = costs
        self.execution = execution
        self.specs: Dict[str, InstrumentSpec] = dict(specs or {})
        self.order_sim = OrderSimulator()
        self.position_sim = PositionSimulator(costs)

        self.open_positions: Dict[str, SimulatedPosition] = {}
        self.closed_trades: List[ClosedTrade] = []
        self.equity_curve: List[EquityPoint] = []
        self.rejected: List[Dict] = []

        self._peak_equity: Decimal = account_config.starting_balance
        self._peak_balance: Decimal = account_config.starting_balance
        self._trade_counter = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _spec(self, symbol: str) -> Optional[InstrumentSpec]:
        return self.specs.get(symbol)

    def _profit_currency(self, symbol: str) -> str:
        spec = self._spec(symbol)
        if spec is not None and spec.quote_currency:
            return spec.quote_currency
        return self.currency

    def _contract_size(self, symbol: str) -> Decimal:
        spec = self._spec(symbol)
        if spec is not None and spec.contract_size:
            return spec.contract_size
        return Decimal("1")

    def _new_position_id(self) -> str:
        return f"pos-{uuid.uuid4().hex[:12]}"

    def has_position(self, symbol: str) -> bool:
        return any(p.symbol == symbol and p.is_open for p in self.open_positions.values())

    def positions_for(self, symbol: str) -> List[SimulatedPosition]:
        return [p for p in self.open_positions.values() if p.symbol == symbol and p.is_open]

    # ------------------------------------------------------------------
    # Opening
    # ------------------------------------------------------------------

    def open_position(
        self,
        symbol: str,
        side: OrderSide,
        volume: Decimal,
        fill_price: Decimal,
        fill_time: datetime,
        stop_loss_price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
        strategy_name: str = "",
        signal_id: str = "",
        risk_amount: Optional[Decimal] = None,
        entry_slippage_price: Decimal = Decimal("0"),
    ) -> Optional[SimulatedPosition]:
        """Open a simulated position. Returns None (and records a rejection) if
        refused (e.g. netting mode with an existing position on the symbol)."""
        if self.position_mode == "netting" and self.has_position(symbol):
            self.rejected.append({
                "symbol": symbol,
                "reason": "netting mode: position already open for symbol",
            })
            return None

        position = SimulatedPosition(
            position_id=self._new_position_id(),
            symbol=symbol,
            side=side,
            volume=volume,
            entry_price=fill_price,
            entry_time=fill_time,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            strategy_name=strategy_name,
            signal_id=signal_id,
            slippage=entry_slippage_price * volume,
            remaining_volume=volume,
            metadata={
                "profit_currency": self._profit_currency(symbol),
                "contract_size": str(self._contract_size(symbol)),
                "risk_amount": str(risk_amount) if risk_amount is not None else None,
            },
        )
        self.open_positions[position.position_id] = position
        return position

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------

    def _exit_slippage_quote(self, exit_slippage_price: Decimal, volume: Decimal) -> Decimal:
        return exit_slippage_price * volume

    def close_position(
        self,
        position: SimulatedPosition,
        exit_price: Decimal,
        exit_time: datetime,
        exit_reason: ExitReason,
        exit_slippage_price: Decimal = Decimal("0"),
        ambiguous: bool = False,
    ) -> ClosedTrade:
        position.slippage += self._exit_slippage_quote(exit_slippage_price, position.volume)
        position.exit_price = exit_price
        position.exit_time = exit_time
        position.exit_reason = exit_reason
        position.ambiguous_exit = ambiguous
        position.status = PositionStatus.CLOSED

        risk_amount = position.metadata.get("risk_amount")
        risk_amount_dec = Decimal(risk_amount) if risk_amount else None

        self._trade_counter += 1
        trade = self.position_sim.build_closed_trade(
            position=position,
            exit_price=exit_price,
            exit_time=exit_time,
            exit_reason=exit_reason,
            trade_id=f"trade-{self._trade_counter}",
            risk_amount=risk_amount_dec,
        )
        self.closed_trades.append(trade)
        self.balance += trade.net_pnl_account
        self._peak_balance = max(self._peak_balance, self.balance)
        self.open_positions.pop(position.position_id, None)
        return trade

    def check_exits(self, symbol: str, bar: OHLCBar) -> List[ClosedTrade]:
        """Check stop-loss / take-profit for all open positions of a symbol."""
        closed: List[ClosedTrade] = []
        for position in list(self.positions_for(symbol)):
            result = self.execution.check_exit(position, bar)
            if result is None:
                continue
            if not result.fill:
                # Ambiguous + SKIP policy: leave open, flag it.
                position.ambiguous_exit = True
                continue
            trade = self.close_position(
                position,
                exit_price=result.price,
                exit_time=bar.timestamp,
                exit_reason=result.reason,
                exit_slippage_price=result.slippage,
                ambiguous=result.ambiguous,
            )
            closed.append(trade)
        return closed

    def close_all(self, prices: Dict[str, Decimal], time: datetime, reason: ExitReason = ExitReason.END_OF_DATA) -> List[ClosedTrade]:
        """Close every open position at the supplied reference prices."""
        closed: List[ClosedTrade] = []
        for position in list(self.open_positions.values()):
            ref = prices.get(position.symbol, position.entry_price)
            trade = self.close_position(position, exit_price=ref, exit_time=time, exit_reason=reason)
            closed.append(trade)
        return closed

    # ------------------------------------------------------------------
    # Valuation
    # ------------------------------------------------------------------

    def unrealized_pnl(self, prices: Dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for position in self.open_positions.values():
            price = prices.get(position.symbol, position.entry_price)
            gross_quote = self.position_sim.gross_pnl_quote(position, price)
            converted = self.costs.converter.convert(
                gross_quote, position.metadata.get("profit_currency", self.currency)
            )
            total += converted if converted is not None else gross_quote
        return total

    def equity(self, prices: Dict[str, Decimal]) -> Decimal:
        return self.balance + self.unrealized_pnl(prices)

    def used_margin(self, prices: Dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for position in self.open_positions.values():
            price = prices.get(position.symbol, position.entry_price)
            contract_size = self._contract_size(position.symbol)
            notional_quote = position.volume * price * contract_size
            converted = self.costs.converter.convert(
                notional_quote, position.metadata.get("profit_currency", self.currency)
            )
            if converted is not None:
                total += converted / self.leverage if self.leverage > 0 else Decimal("0")
        return total

    def free_margin(self, prices: Dict[str, Decimal]) -> Decimal:
        return self.equity(prices) - self.used_margin(prices)

    def account_snapshot(self, prices: Dict[str, Decimal], timestamp: datetime) -> AccountSnapshot:
        equity = self.equity(prices)
        margin = self.used_margin(prices)
        return AccountSnapshot(
            login=0,
            name="SimulatedBacktestAccount",
            server="backtest",
            currency=self.currency,
            balance=self.balance,
            equity=equity,
            margin=margin,
            free_margin=equity - margin,
            margin_level=(equity / margin * Decimal("100")) if margin > 0 else None,
            trade_allowed=True,
            trade_mode="demo",
            leverage=self.leverage,
            timestamp=timestamp,
            data_source="backtest",
        )

    # ------------------------------------------------------------------
    # Equity curve
    # ------------------------------------------------------------------

    def record_equity_point(
        self,
        timestamp: datetime,
        prices: Dict[str, Decimal],
        open_positions: Optional[int] = None,
    ) -> EquityPoint:
        equity = self.equity(prices)
        margin = self.used_margin(prices)
        self._peak_equity = max(self._peak_equity, equity)
        drawdown = Decimal("0")
        if self._peak_equity > 0:
            drawdown = (self._peak_equity - equity) / self._peak_equity * Decimal("100")
        point = EquityPoint(
            timestamp=timestamp,
            equity=equity,
            balance=self.balance,
            margin=margin,
            free_margin=equity - margin,
            open_positions=open_positions if open_positions is not None else len(self.open_positions),
            drawdown_percent=drawdown,
        )
        self.equity_curve.append(point)
        return point