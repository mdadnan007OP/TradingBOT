"""Order simulator.

Tracks simulated orders (pending market / pending limit) and their lifecycle.
Orders are never sent to a broker; they only exist in internal state.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from src.backtesting.models import (
    OrderSide,
    OrderStatus,
    OrderType,
    SimulatedOrder,
)


class OrderSimulator:
    """Bookkeeping for simulated orders."""

    def __init__(self) -> None:
        self._orders: Dict[str, SimulatedOrder] = {}

    def new_id(self) -> str:
        return f"ord-{uuid.uuid4().hex[:12]}"

    def submit(
        self,
        symbol: str,
        side: OrderSide,
        volume,
        order_type: OrderType = OrderType.MARKET,
        requested_price=None,
        stop_loss_price=None,
        take_profit_price=None,
        strategy_name: str = "",
        signal_id: str = "",
        created_at: Optional[datetime] = None,
    ) -> SimulatedOrder:
        order = SimulatedOrder(
            order_id=self.new_id(),
            symbol=symbol,
            side=side,
            order_type=order_type,
            volume=volume,
            requested_price=requested_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            status=OrderStatus.PENDING,
            created_at=created_at,
            strategy_name=strategy_name,
            signal_id=signal_id,
        )
        self._orders[order.order_id] = order
        return order

    def get(self, order_id: str) -> Optional[SimulatedOrder]:
        return self._orders.get(order_id)

    def pending(self, symbol: Optional[str] = None) -> List[SimulatedOrder]:
        return [
            o for o in self._orders.values()
            if o.status == OrderStatus.PENDING
            and (symbol is None or o.symbol == symbol)
        ]

    def all_orders(self) -> List[SimulatedOrder]:
        return list(self._orders.values())

    def mark_filled(self, order_id: str, fill_price, filled_at: datetime) -> Optional[SimulatedOrder]:
        order = self._orders.get(order_id)
        if order is None:
            return None
        order.status = OrderStatus.FILLED
        order.fill_price = fill_price
        order.filled_at = filled_at
        return order

    def mark_rejected(self, order_id: str, reason: str) -> Optional[SimulatedOrder]:
        order = self._orders.get(order_id)
        if order is None:
            return None
        order.status = OrderStatus.REJECTED
        order.reject_reason = reason
        return order

    def cancel(self, order_id: str) -> Optional[SimulatedOrder]:
        order = self._orders.get(order_id)
        if order is None or order.status != OrderStatus.PENDING:
            return None
        order.status = OrderStatus.CANCELLED
        return order

    def cancel_all_pending(self, symbol: Optional[str] = None) -> int:
        count = 0
        for order in self.pending(symbol):
            order.status = OrderStatus.CANCELLED
            count += 1
        return count