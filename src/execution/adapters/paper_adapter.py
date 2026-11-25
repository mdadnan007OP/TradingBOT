"""Phase 9 PAPER execution adapter.

Simulated execution only. Never calls order_send() or order_check(). Maintains
paper account state, simulates entries/exits/positions, and reuses Phase 8
simulation components where possible. Safe even when DEMO config vars exist.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.execution.account_identity import AccountIdentity
from src.execution.emergency_stop import EmergencyControls
from src.execution.interfaces import ExecutionGateway
from src.execution.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    OrderFillPolicy,
    BrokerRetCode,
)
from src.models import (
    AccountInfo,
    Instrument,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Tick,
    TradeResult,
    TradeResultModel,
)


@dataclass
class PaperPosition:
    position_id: str
    symbol: str
    side: OrderSide
    volume: Decimal
    entry_price: Decimal
    entry_time: datetime
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    magic_number: int
    comment: str


class PaperExecutionAdapter(ExecutionGateway):
    """Paper-trading execution adapter (simulated, no broker access)."""

    def __init__(self, starting_balance: Decimal = Decimal("100000")) -> None:
        self._connected = False
        self._balance = starting_balance
        self._equity = starting_balance
        self._positions: Dict[str, PaperPosition] = {}
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._ticket_counter = 1
        self._fills: List[Dict[str, Any]] = []
        self._mode = "PAPER"
        self._name = "PaperExecutionAdapter"

    # ------------------------------------------------------------------
    # Gateway interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def mode(self) -> str:
        return self._mode

    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def can_submit_orders(self) -> bool:
        # PAPER never submits to a broker.
        return False

    # --- account / market ---------------------------------------------
    def get_account_info(self) -> Optional[AccountInfo]:
        if not self._connected:
            return None
        return AccountInfo(
            login=0,
            name="Paper Account",
            server="PAPER",
            currency="USD",
            balance=self._balance,
            equity=self._equity,
            margin=Decimal("0"),
            free_margin=self._equity,
            margin_level=None,
            trade_allowed=True,
            trade_mode="demo",
        )

    def get_instruments(self) -> List[Instrument]:
        if not self._connected:
            return []
        return [
            Instrument(symbol="EURUSD", name="Euro vs US Dollar", instrument_type="forex",
                       base_currency="EUR", quote_currency="USD",
                       point=Decimal("0.00001"), min_lot=Decimal("0.01"),
                       max_lot=Decimal("100.0"), lot_step=Decimal("0.01")),
            Instrument(symbol="XAUUSD", name="Gold vs US Dollar", instrument_type="metal",
                       base_currency="XAU", quote_currency="USD",
                       point=Decimal("0.01"), min_lot=Decimal("0.01"),
                       max_lot=Decimal("500.0"), lot_step=Decimal("0.01")),
        ]

    def get_tick(self, symbol: str) -> Optional[Tick]:
        if not self._connected:
            return None
        base = {"EURUSD": Decimal("1.0850"), "XAUUSD": Decimal("2000.00")}.get(
            symbol, Decimal("1.0")
        )
        spread = Decimal("0.0002") if symbol == "EURUSD" else Decimal("0.03")
        bid = base - spread / 2
        ask = base + spread / 2
        return Tick(symbol=symbol, bid=bid, ask=ask, timestamp=datetime.now(timezone.utc))

    def get_symbol_spec(self, symbol: str) -> Optional[Dict[str, Any]]:
        specs = {
            "EURUSD": {
                "point": Decimal("0.00001"),
                "tick_size": Decimal("0.00001"),
                "lot_step": Decimal("0.01"),
                "min_lot": Decimal("0.01"),
                "max_lot": Decimal("100.0"),
                "contract_size": Decimal("100000"),
                "stop_level": Decimal("0"),
                "trade_mode": "full",
            },
            "XAUUSD": {
                "point": Decimal("0.01"),
                "tick_size": Decimal("0.01"),
                "lot_step": Decimal("0.01"),
                "min_lot": Decimal("0.01"),
                "max_lot": Decimal("500.0"),
                "contract_size": Decimal("100"),
                "stop_level": Decimal("0"),
                "trade_mode": "full",
            },
        }
        return specs.get(symbol)

    # --- order lifecycle (simulated) ----------------------------------
    def order_check(self, request: OrderRequest) -> ExecutionResult:
        """Non-submitting preflight (simulated). Never a trade."""
        if not self._connected:
            return ExecutionResult(
                execution_id="paper",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=-1,
                error_message="Paper adapter not connected",
            )
        # Simulate acceptance if volume within bounds.
        spec = self.get_symbol_spec(request.symbol)
        if spec is None:
            return ExecutionResult(
                execution_id="paper",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=404,
                error_message=f"Unknown symbol {request.symbol}",
            )
        if request.volume < spec["min_lot"] or request.volume > spec["max_lot"]:
            return ExecutionResult(
                execution_id="paper",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=10014,  # INVALID_VOLUME
                error_message="Invalid volume",
            )
        return ExecutionResult(
            execution_id="paper",
            success=True,
            state=ExecutionState.ACCEPTED,
            price=request.price,
            volume=request.volume,
            error_message="Paper preflight accepted (simulated)",
        )

    def order_send(self, request: OrderRequest) -> ExecutionResult:
        """PAPER never submits to a broker. Simulates a fill instead."""
        if not self._connected:
            return ExecutionResult(
                execution_id="paper",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=-1,
                error_message="Paper adapter not connected",
            )
        spec = self.get_symbol_spec(request.symbol)
        if spec is None:
            return ExecutionResult(
                execution_id="paper",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=404,
                error_message=f"Unknown symbol {request.symbol}",
            )
        # Validate volume against broker spec.
        if request.volume < spec["min_lot"] or request.volume > spec["max_lot"]:
            return ExecutionResult(
                execution_id="paper",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=10014,  # INVALID_VOLUME
                error_message="Invalid volume",
            )
        # Simulate fill at requested price (no slippage in paper by default).
        ticket = str(self._ticket_counter)
        self._ticket_counter += 1
        position = PaperPosition(
            position_id=ticket,
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            entry_price=request.price or Decimal("0"),
            entry_time=datetime.now(timezone.utc),
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            magic_number=request.magic_number or 0,
            comment=request.comment or "",
        )
        self._positions[ticket] = position
        self._orders[ticket] = {
            "ticket": ticket,
            "symbol": request.symbol,
            "side": request.side,
            "order_type": request.order_type,
            "volume": request.volume,
            "status": OrderStatus.FILLED,
            "price": request.price,
            "stop_loss": request.stop_loss,
            "take_profit": request.take_profit,
            "open_time": datetime.now(timezone.utc),
            "comment": request.comment,
            "magic_number": request.magic_number,
        }
        self._fills.append(
            {
                "ticket": ticket,
                "symbol": request.symbol,
                "side": request.side.value,
                "volume": str(request.volume),
                "price": str(request.price or Decimal("0")),
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )
        # Update equity (simulated PnL = 0 at entry; no cost model).
        return ExecutionResult(
            execution_id=ticket,
            success=True,
            state=ExecutionState.FILLED,
            ticket=ticket,
            symbol=request.symbol,
            volume=request.volume,
            price=request.price,
            filled_volume=request.volume,
            filled_price=request.price,
            broker_retcode=BrokerRetCode.DONE,
            broker_comment="Paper simulated fill (no broker)",
            reconciled=False,
            retry_permitted=False,
        )

    def get_orders(self) -> List[Order]:
        if not self._connected:
            return []
        return [self._to_order(o) for o in self._orders.values()]

    def get_positions(self) -> List[Position]:
        if not self._connected:
            return []
        out = []
        for p in self._positions.values():
            out.append(
                Position(
                    ticket=p.position_id,
                    symbol=p.symbol,
                    side=p.side,
                    volume=p.volume,
                    open_price=p.entry_price,
                    current_price=p.entry_price,
                    stop_loss=p.stop_loss,
                    take_profit=p.take_profit,
                    profit=Decimal("0"),
                    open_time=p.entry_time,
                    comment=p.comment,
                    magic_number=p.magic_number,
                )
            )
        return out

    def get_history_orders(self) -> List[Order]:
        return self.get_orders()

    def get_history_deals(self) -> List[Dict[str, Any]]:
        return list(self._fills)

    # ------------------------------------------------------------------
    # Paper-specific reporting
    # ------------------------------------------------------------------

    def paper_report(self) -> Dict[str, Any]:
        return {
            "mode": "PAPER",
            "balance": str(self._balance),
            "equity": str(self._equity),
            "open_positions": len(self._positions),
            "total_orders": len(self._orders),
            "fills": len(self._fills),
            "disclaimer": "Paper trading results are simulated and not indicative of real performance.",
        }

    def _to_order(self, d: Dict[str, Any]) -> Order:
        return Order(
            ticket=d["ticket"],
            symbol=d["symbol"],
            side=d["side"],
            order_type=d["order_type"],
            volume=d["volume"],
            status=d["status"],
            price=d["price"],
            stop_loss=d["stop_loss"],
            take_profit=d["take_profit"],
            open_time=d["open_time"],
            comment=d["comment"],
            magic_number=d["magic_number"],
        )
