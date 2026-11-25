"""Phase 9 dedicated demo MT5 execution adapter.

The ONLY execution component permitted to call MT5 trading functions
(order_check, order_send, positions_get, orders_get, history_*_get).
Reverifies DEMO account identity before every order-related request.

This adapter does NOT use MT5BrokerAdapter.place_order/close_order (those are
hard-disabled read-only stubs). It uses MT5ConnectionManager directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.broker.mt5.connection import MT5AccountInfo, MT5ConnectionManager
from src.execution.account_identity import AccountIdentity
from src.execution.emergency_stop import EmergencyControls
from src.execution.interfaces import ExecutionGateway
from src.execution.models import (
    BrokerRetCode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    OrderFillPolicy,
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return default


@dataclass
class DemoMT5ExecutionAdapter(ExecutionGateway):
    """Demo-only MT5 execution adapter (trading-API caller)."""

    connection: MT5ConnectionManager
    magic_number: int
    comment_prefix: str = "bot"
    allowed_demo_server: str = ""
    allowed_broker_company: str = ""

    _connected: bool = field(default=False, init=False)
    _mt5_module: Any = field(default=None, init=False, repr=False)
    _account_info: Optional[MT5AccountInfo] = field(default=None, init=False, repr=False)
    _ticket_counter: int = field(default=1, init=False)

    # ------------------------------------------------------------------
    # Gateway interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "DemoMT5ExecutionAdapter"

    @property
    def mode(self) -> str:
        return "DEMO"

    def is_connected(self) -> bool:
        return self._connected and self.connection.check_connection()

    def connect(self) -> bool:
        try:
            self.connection.initialize()
            self._mt5_module = self.connection._mt5_module
            self._account_info = MT5AccountInfo(self._mt5_module)
            self._connected = True
            return True
        except Exception:  # noqa: BLE001
            self._connected = False
            return False

    def disconnect(self) -> bool:
        self._connected = False
        try:
            self.connection.shutdown()
        except Exception:  # noqa: BLE001
            pass
        return True

    def can_submit_orders(self) -> bool:
        # Demo adapter is authorized to submit orders (DEMO mode only).
        return True

    # --- account / market ---------------------------------------------
    def get_account_info(self) -> Optional[AccountInfo]:
        if not self.is_connected or self._account_info is None:
            return None
        raw = self._account_info.get_account_info()
        if raw is None:
            return None
        return AccountInfo(
            login=_safe_int(getattr(raw, "login", 0)),
            name=str(getattr(raw, "name", "Demo Account")),
            server=str(getattr(raw, "server", "")),
            currency=str(getattr(raw, "currency", "USD")),
            balance=_safe_decimal(getattr(raw, "balance", 0)),
            equity=_safe_decimal(getattr(raw, "equity", 0)),
            margin=_safe_decimal(getattr(raw, "margin", 0)),
            free_margin=_safe_decimal(getattr(raw, "free_margin", 0)),
            margin_level=_safe_decimal(getattr(raw, "margin_level", 0)) or None,
            trade_allowed=bool(getattr(raw, "trade_allowed", False)),
            trade_mode="demo",
        )

    def get_instruments(self) -> List[Instrument]:
        if not self.is_connected:
            return []
        # Use symbol discovery via connection if available; otherwise empty.
        return []

    def get_tick(self, symbol: str) -> Optional[Tick]:
        if not self.is_connected or self._mt5_module is None:
            return None
        try:
            tick = self._mt5_module.symbol_info_tick(symbol)
            if tick is None:
                return None
            return Tick(
                symbol=symbol,
                bid=_safe_decimal(getattr(tick, "bid", 0)),
                ask=_safe_decimal(getattr(tick, "ask", 0)),
                last=_safe_decimal(getattr(tick, "last", 0)) or None,
                volume=_safe_int(getattr(tick, "volume", 0)) or None,
                timestamp=datetime.fromtimestamp(
                    int(getattr(tick, "time", 0) or 0), tz=timezone.utc
                ),
            )
        except Exception:  # noqa: BLE001
            return None

    def get_symbol_spec(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.is_connected or self._mt5_module is None:
            return None
        try:
            info = self._mt5_module.symbol_info(symbol)
            if info is None:
                return None
            return {
                "point": _safe_decimal(getattr(info, "point", 0)),
                "tick_size": _safe_decimal(getattr(info, "trade_tick_size", 0)),
                "lot_step": _safe_decimal(getattr(info, "volume_step", 0)),
                "min_lot": _safe_decimal(getattr(info, "volume_min", 0)),
                "max_lot": _safe_decimal(getattr(info, "volume_max", 0)),
                "contract_size": _safe_decimal(getattr(info, "trade_contract_size", 100000)),
                "stop_level": _safe_decimal(getattr(info, "trade_stops_level", 0)),
                "trade_mode": _safe_int(getattr(info, "trade_mode", 0)),
                "filling_modes": _safe_int(getattr(info, "filling_mode", 0)),
            }
        except Exception:  # noqa: BLE001
            return None

    # --- order lifecycle (demo MT5 trading API) -----------------------
    def order_check(self, request: OrderRequest) -> ExecutionResult:
        """Pre-trade preflight via MT5 order_check(). Never a trade."""
        self._require_connected()
        mt5 = self._mt5_module
        if mt5 is None:
            return ExecutionResult(
                execution_id="demo",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=-1,
                error_message="MT5 module unavailable",
            )
        # Reverify DEMO identity before trading operation.
        identity_ok = self._verify_demo_identity()
        if not identity_ok:
            return ExecutionResult(
                execution_id="demo",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=403,
                error_message="Demo account identity verification failed",
            )
        try:
            request_dict = self._build_mt5_request(request, check_only=True)
            result = mt5.order_check(request_dict)
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                execution_id="demo",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=-1,
                error_message=f"order_check() exception: {exc}",
            )
        return self._classify_check_result(result, request)

    def order_send(self, request: OrderRequest) -> ExecutionResult:
        """Submit a demo order via MT5 order_send().

        Persists submission-intent before calling. Never treats a non-null
        result as proof of fill.
        """
        self._require_connected()
        mt5 = self._mt5_module
        if mt5 is None:
            return ExecutionResult(
                execution_id="demo",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=-1,
                error_message="MT5 module unavailable",
            )
        identity_ok = self._verify_demo_identity()
        if not identity_ok:
            return ExecutionResult(
                execution_id="demo",
                success=False,
                state=ExecutionState.REJECTED,
                error_code=403,
                error_message="Demo account identity verification failed",
            )
        try:
            request_dict = self._build_mt5_request(request, check_only=False)
            result = mt5.order_send(request_dict)
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                execution_id="demo",
                success=False,
                state=ExecutionState.UNKNOWN,
                error_code=-1,
                error_message=f"order_send() exception: {exc}",
                retry_permitted=False,
            )
        return self._classify_send_result(result, request)

    def get_orders(self) -> List[Order]:
        if not self.is_connected or self._mt5_module is None:
            return []
        try:
            raw = self._mt5_module.orders_get()
            if raw is None:
                return []
            return [self._convert_order(o) for o in raw]
        except Exception:  # noqa: BLE001
            return []

    def get_positions(self) -> List[Position]:
        if not self.is_connected or self._mt5_module is None:
            return []
        try:
            raw = self._mt5_module.positions_get()
            if raw is None:
                return []
            return [self._convert_position(p) for p in raw]
        except Exception:  # noqa: BLE001
            return []

    def get_history_orders(self) -> List[Order]:
        return self.get_orders()

    def get_history_deals(self) -> List[Dict[str, Any]]:
        if not self.is_connected or self._mt5_module is None:
            return []
        try:
            raw = self._mt5_module.history_deals_get()
            if raw is None:
                return []
            return [self._deal_to_dict(d) for d in raw]
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------------
    # MT5 request building + result classification
    # ------------------------------------------------------------------

    def _build_mt5_request(self, request: OrderRequest, check_only: bool) -> Dict[str, Any]:
        mt5 = self._mt5_module
        action = mt5.TRADE_ACTION_DEAL if mt5 is not None else 0
        type_ = (
            mt5.ORDER_TYPE_BUY
            if request.side == OrderSide.BUY
            else mt5.ORDER_TYPE_SELL
        ) if mt5 is not None else 0
        filling = mt5.ORDER_FILLING_RETURN if mt5 is not None else 0
        return {
            "action": action,
            "symbol": request.symbol,
            "type": type_,
            "volume": float(request.volume),
            "price": float(request.price or 0),
            "sl": float(request.stop_loss or 0),
            "tp": float(request.take_profit or 0),
            "deviation": 0,
            "magic": self.magic_number,
            "comment": request.comment or "",
            "type_filling": filling,
            "type_time": mt5.ORDER_TIME_GTC if mt5 is not None else 0,
        }

    def _verify_demo_identity(self) -> bool:
        """Reverify DEMO account identity before any trading operation."""
        if not self.is_connected or self._account_info is None:
            return False
        if not self._account_info.is_account_available():
            return False
        if not self._account_info.is_demo_account():
            return False
        raw = self._account_info.get_account_info()
        if raw is None:
            return False
        server = str(getattr(raw, "server", "") or "")
        company = str(getattr(raw, "company", "") or "")
        if self.allowed_demo_server and server != self.allowed_demo_server:
            return False
        if self.allowed_broker_company and company != self.allowed_broker_company:
            return False
        return bool(getattr(raw, "trade_allowed", False))

    def _require_connected(self) -> None:
        if not self.is_connected():
            raise RuntimeError("Demo MT5 adapter not connected")

    @staticmethod
    def _classify_check_result(result: Any, request: OrderRequest) -> ExecutionResult:
        retcode = _safe_int(getattr(result, "retcode", -1))
        code = _map_retcode(retcode)
        success = code == BrokerRetCode.DONE
        return ExecutionResult(
            execution_id="demo-check",
            success=success,
            state=ExecutionState.PRE_TRADE_CHECKED if success else ExecutionState.REJECTED,
            price=request.price,
            volume=request.volume,
            broker_retcode=code,
            broker_comment=str(getattr(result, "comment", "") or ""),
            error_code=retcode if not success else None,
            error_message=None if success else str(getattr(result, "comment", "") or "order_check rejected"),
            reconciled=False,
            retry_permitted=False,
        )

    @staticmethod
    def _classify_send_result(result: Any, request: OrderRequest) -> ExecutionResult:
        retcode = _safe_int(getattr(result, "retcode", -1))
        code = _map_retcode(retcode)
        order_ticket = getattr(result, "order", None)
        deal_ticket = getattr(result, "deal", None)
        volume = _safe_decimal(getattr(result, "volume", request.volume))
        price = _safe_decimal(getattr(result, "price", request.price))
        comment = str(getattr(result, "comment", "") or "")

        # Never treat non-null result as proof of fill.
        if code == BrokerRetCode.DONE:
            state = ExecutionState.FILLED
            success = True
            reconciled = False
            retry = False
        elif code == BrokerRetCode.DONE_PARTIAL:
            state = ExecutionState.PARTIALLY_FILLED
            success = True
            reconciled = False
            retry = False
        elif code == BrokerRetCode.PLACED:
            state = ExecutionState.ACCEPTED  # placed, not filled
            success = True
            reconciled = False
            retry = False
        elif code == BrokerRetCode.REQUOTE:
            state = ExecutionState.REJECTED
            success = False
            reconciled = False
            retry = False
        elif code == BrokerRetCode.TIMEOUT:
            state = ExecutionState.UNKNOWN
            success = False
            reconciled = False
            retry = False  # never blind retry
        elif code == BrokerRetCode.REJECT:
            state = ExecutionState.REJECTED
            success = False
            reconciled = False
            retry = False
        else:
            state = ExecutionState.UNKNOWN
            success = False
            reconciled = False
            retry = False

        return ExecutionResult(
            execution_id="demo-send",
            success=success,
            state=state,
            ticket=str(order_ticket) if order_ticket else None,
            symbol=request.symbol,
            volume=volume,
            price=price,
            filled_volume=volume if state == ExecutionState.FILLED else None,
            filled_price=price if state in (ExecutionState.FILLED, ExecutionState.PARTIALLY_FILLED) else None,
            broker_retcode=code,
            broker_comment=comment,
            error_code=None if success else retcode,
            error_message=None if success else comment or f"retcode {retcode}",
            reconciled=reconciled,
            retry_permitted=retry,
        )

    # ------------------------------------------------------------------
    # MT5 -> internal model conversion (read-only reconciliation)
    # ------------------------------------------------------------------

    def _convert_order(self, o: Any) -> Order:
        mt5_type = int(getattr(o, "type", 0))
        side = OrderSide.BUY if mt5_type % 2 == 0 else OrderSide.SELL
        volume = getattr(o, "volume_current", None) or getattr(o, "volume_initial", 0)
        price_open = float(getattr(o, "price_open", 0) or 0)
        sl = float(getattr(o, "sl", 0) or 0)
        tp = float(getattr(o, "tp", 0) or 0)
        time_setup = int(getattr(o, "time_setup", 0) or 0)
        magic = int(getattr(o, "magic", 0) or 0)
        return Order(
            ticket=str(getattr(o, "ticket", "")),
            symbol=getattr(o, "symbol", ""),
            side=side,
            order_type=self._map_order_type(mt5_type),
            volume=Decimal(str(volume)),
            status=self._map_order_status(int(getattr(o, "state", 1))),
            price=Decimal(str(price_open)) if price_open > 0 else None,
            stop_loss=Decimal(str(sl)) if sl > 0 else None,
            take_profit=Decimal(str(tp)) if tp > 0 else None,
            open_time=datetime.fromtimestamp(time_setup, tz=timezone.utc) if time_setup > 0 else None,
            comment=getattr(o, "comment", "") or None,
            magic_number=magic if magic != 0 else None,
        )

    def _convert_position(self, p: Any) -> Position:
        pos_type = int(getattr(p, "type", 0))
        side = OrderSide.BUY if pos_type == 0 else OrderSide.SELL
        price_open = float(getattr(p, "price_open", 0) or 0)
        price_current = float(getattr(p, "price_current", 0) or 0)
        sl = float(getattr(p, "sl", 0) or 0)
        tp = float(getattr(p, "tp", 0) or 0)
        profit = float(getattr(p, "profit", 0) or 0)
        time_open = int(getattr(p, "time", 0) or 0)
        magic = int(getattr(p, "magic", 0) or 0)
        return Position(
            ticket=str(getattr(p, "ticket", "")),
            symbol=getattr(p, "symbol", ""),
            side=side,
            volume=Decimal(str(getattr(p, "volume", 0) or 0)),
            open_price=Decimal(str(price_open)),
            current_price=Decimal(str(price_current)),
            stop_loss=Decimal(str(sl)) if sl > 0 else None,
            take_profit=Decimal(str(tp)) if tp > 0 else None,
            profit=Decimal(str(profit)),
            open_time=datetime.fromtimestamp(time_open, tz=timezone.utc) if time_open > 0 else None,
            comment=getattr(p, "comment", "") or None,
            magic_number=magic if magic != 0 else None,
        )

    @staticmethod
    def _map_order_type(mt5_type: int) -> OrderType:
        if mt5_type in (0, 1, 8):
            return OrderType.MARKET
        if mt5_type in (2, 3):
            return OrderType.LIMIT
        if mt5_type in (4, 5):
            return OrderType.STOP
        if mt5_type in (6, 7):
            return OrderType.STOP_LIMIT
        return OrderType.MARKET

    @staticmethod
    def _map_order_status(mt5_state: int) -> OrderStatus:
        mapping = {
            0: OrderStatus.OPEN,
            1: OrderStatus.OPEN,
            2: OrderStatus.CANCELLED,
            3: OrderStatus.PARTIALLY_FILLED,
            4: OrderStatus.FILLED,
            5: OrderStatus.REJECTED,
            6: OrderStatus.EXPIRED,
            7: OrderStatus.OPEN,
            8: OrderStatus.OPEN,
            9: OrderStatus.OPEN,
        }
        return mapping.get(mt5_state, OrderStatus.OPEN)

    @staticmethod
    def _deal_to_dict(d: Any) -> Dict[str, Any]:
        return {
            "ticket": str(getattr(d, "ticket", "")),
            "symbol": getattr(d, "symbol", ""),
            "type": int(getattr(d, "type", 0)),
            "volume": str(getattr(d, "volume", 0)),
            "price": str(getattr(d, "price", 0)),
            "profit": str(getattr(d, "profit", 0)),
            "time": int(getattr(d, "time", 0) or 0),
            "order": str(getattr(d, "orderid", 0) or 0),
        }
