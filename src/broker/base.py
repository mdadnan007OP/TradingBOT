"""Broker integration layer.

Defines the ``BrokerAdapter`` interface that all broker implementations must
satisfy, plus a ``MockBrokerAdapter`` for testing and development. The MT5
adapter (Phase 2) will implement the same interface.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from src.models import (
    AccountInfo,
    Candle,
    Instrument,
    InstrumentType,
    Order,
    OrderRequest,
    OrderStatus,
    Position,
    Tick,
    TradeResult,
    TradeResultModel,
)

logger = logging.getLogger(__name__)


class BrokerAdapter(ABC):
    """Abstract interface every broker adapter must implement.

    Keep this broker-agnostic. The MT5 adapter (Phase 2) translates these calls
    into MetaTrader 5 terminal API calls; the mock adapter simulates them.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable broker adapter name."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the adapter is currently connected to the broker."""

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the broker. Return True on success."""

    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from the broker. Return True on success."""

    @abstractmethod
    def get_account_info(self) -> Optional[AccountInfo]:
        """Return current account information, or None on failure."""

    @abstractmethod
    def get_instruments(self) -> List[Instrument]:
        """Return the list of tradable instruments the broker offers."""

    @abstractmethod
    def get_tick(self, symbol: str) -> Optional[Tick]:
        """Return the latest tick for ``symbol``, or None if unavailable."""

    @abstractmethod
    def get_candles(self, symbol: str, count: int) -> List[Candle]:
        """Return the most recent ``count`` candles for ``symbol``."""

    @abstractmethod
    def place_order(self, request: OrderRequest) -> TradeResultModel:
        """Submit an order request and return the result."""

    @abstractmethod
    def close_order(self, ticket: str) -> TradeResultModel:
        """Close an open order by ticket. Return the result."""

    @abstractmethod
    def get_orders(self) -> List[Order]:
        """Return all known orders (open and history)."""

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Return all open positions."""


class MockBrokerAdapter(BrokerAdapter):
    """In-memory mock broker for development and testing.

    Simulates connection, account info, instruments, ticks, candles, order
    placement, and position tracking without touching any real market or
    broker. Safe to use with no credentials.
    """

    def __init__(self, initial_balance: Decimal = Decimal("10000.0")) -> None:
        self._connected = False
        self._initial_balance = initial_balance
        self._instruments: Dict[str, Instrument] = {}
        self._ticks: Dict[str, Tick] = {}
        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Position] = {}
        self._next_ticket = 1
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # --- connection -------------------------------------------------------

    @property
    def name(self) -> str:
        return "MockBroker"

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        self._logger.info("Mock broker connected")
        return True

    def disconnect(self) -> bool:
        self._connected = False
        self._logger.info("Mock broker disconnected")
        return True

    # --- account / instruments -------------------------------------------

    def get_account_info(self) -> Optional[AccountInfo]:
        if not self._connected:
            self._logger.warning("get_account_info called while disconnected")
            return None
        return AccountInfo(
            login=123456,
            name="Mock Demo Account",
            server="Mock-Server",
            currency="USD",
            balance=self._initial_balance,
            equity=self._initial_balance,
            margin=Decimal("0"),
            free_margin=self._initial_balance,
            trade_allowed=True,
            trade_mode="demo",
        )

    def get_instruments(self) -> List[Instrument]:
        if not self._connected:
            return []
        if not self._instruments:
            self._instruments = {
                "XAUUSD": Instrument(
                    symbol="XAUUSD",
                    name="Gold vs US Dollar",
                    instrument_type=InstrumentType.METAL,
                    base_currency="XAU",
                    quote_currency="USD",
                    point=Decimal("0.01"),
                    min_lot=Decimal("0.01"),
                    max_lot=Decimal("500.0"),
                    lot_step=Decimal("0.01"),
                ),
                "XAGUSD": Instrument(
                    symbol="XAGUSD",
                    name="Silver vs US Dollar",
                    instrument_type=InstrumentType.METAL,
                    base_currency="XAG",
                    quote_currency="USD",
                    point=Decimal("0.001"),
                    min_lot=Decimal("0.01"),
                    max_lot=Decimal("1000.0"),
                    lot_step=Decimal("0.01"),
                ),
                "EURUSD": Instrument(
                    symbol="EURUSD",
                    name="Euro vs US Dollar",
                    base_currency="EUR",
                    quote_currency="USD",
                    point=Decimal("0.00001"),
                    min_lot=Decimal("0.01"),
                    max_lot=Decimal("100.0"),
                    lot_step=Decimal("0.01"),
                ),
                "GBPUSD": Instrument(
                    symbol="GBPUSD",
                    name="Great Britain Pound vs US Dollar",
                    base_currency="GBP",
                    quote_currency="USD",
                    point=Decimal("0.00001"),
                    min_lot=Decimal("0.01"),
                    max_lot=Decimal("100.0"),
                    lot_step=Decimal("0.01"),
                ),
                "USDJPY": Instrument(
                    symbol="USDJPY",
                    name="US Dollar vs Japanese Yen",
                    base_currency="USD",
                    quote_currency="JPY",
                    point=Decimal("0.001"),
                    min_lot=Decimal("0.01"),
                    max_lot=Decimal("100.0"),
                    lot_step=Decimal("0.01"),
                ),
            }
        return list(self._instruments.values())

    # --- market data ------------------------------------------------------

    def get_tick(self, symbol: str) -> Optional[Tick]:
        if not self._connected:
            return None
        base_price_map = {
            "XAUUSD": Decimal("2000.00"),
            "XAGUSD": Decimal("25.00"),
            "EURUSD": Decimal("1.0850"),
            "GBPUSD": Decimal("1.2700"),
            "USDJPY": Decimal("148.50"),
        }
        base_price = base_price_map.get(symbol, Decimal("1.0"))

        spread = Decimal("0.0002") if symbol not in ("XAUUSD", "XAGUSD", "USDJPY") else Decimal("0.03")
        bid = base_price - spread / 2
        ask = base_price + spread / 2
        tick = Tick(symbol=symbol, bid=bid, ask=ask, timestamp=datetime.now())
        self._ticks[symbol] = tick
        return tick

    def get_candles(self, symbol: str, count: int) -> List[Candle]:
        if not self._connected or count <= 0:
            return []
        tick = self.get_tick(symbol)
        base = tick.mid if tick else Decimal("1.0")
        candles: List[Candle] = []
        for i in range(count):
            ts = datetime.now()
            open_ = base
            close = base + (Decimal(str(i % 3 - 1)) * Decimal("0.001"))
            high = max(open_, close) + Decimal("0.0005")
            low = min(open_, close) - Decimal("0.0005")
            candles.append(
                Candle(symbol=symbol, open=open_, high=high, low=low, close=close, timestamp=ts)
            )
            base = close
        return candles

    # --- order management -------------------------------------------------

    def place_order(self, request: OrderRequest) -> TradeResultModel:
        if not self._connected:
            return TradeResultModel(
                success=False,
                result=TradeResult.FAILURE,
                error_code=-1,
                error_message="Not connected to broker",
            )

        ticket = str(self._next_ticket)
        self._next_ticket += 1

        order = Order(
            ticket=ticket,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            volume=request.volume,
            status=OrderStatus.OPEN,
            price=request.price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            open_time=datetime.now(),
            comment=request.comment,
            magic_number=request.magic_number,
        )
        self._orders[ticket] = order
        self._positions[ticket] = Position(
            ticket=ticket,
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            open_price=request.price or Decimal("0"),
            current_price=request.price or Decimal("0"),
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            open_time=datetime.now(),
            comment=request.comment,
            magic_number=request.magic_number,
        )

        self._logger.info(
            "Mock order placed: ticket=%s symbol=%s side=%s volume=%s",
            ticket,
            request.symbol,
            request.side.value,
            request.volume,
        )
        return TradeResultModel(
            success=True,
            result=TradeResult.SUCCESS,
            ticket=ticket,
            symbol=request.symbol,
            volume=request.volume,
            price=request.price,
            order=order,
        )

    def close_order(self, ticket: str) -> TradeResultModel:
        if not self._connected:
            return TradeResultModel(
                success=False,
                result=TradeResult.FAILURE,
                error_code=-1,
                error_message="Not connected to broker",
            )
        order = self._orders.get(ticket)
        if order is None:
            return TradeResultModel(
                success=False,
                result=TradeResult.REJECTED,
                error_code=404,
                error_message=f"Order {ticket} not found",
            )
        self._positions.pop(ticket, None)
        self._logger.info("Mock order closed: ticket=%s", ticket)
        return TradeResultModel(success=True, result=TradeResult.SUCCESS, ticket=ticket)

    def get_orders(self) -> List[Order]:
        if not self._connected:
            return []
        return list(self._orders.values())

    def get_positions(self) -> List[Position]:
        if not self._connected:
            return []
        return list(self._positions.values())
