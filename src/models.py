"""Basic data models for the Forex trading bot.

All models are immutable frozen dataclasses where sensible, keeping business
objects free of side effects. These models are broker-agnostic: they describe
concepts (tick, candle, order, position, account) rather than any specific
broker's API shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class InstrumentType(str, Enum):
    FOREX = "forex"
    METAL = "metal"
    CRYPTO = "crypto"
    INDEX = "index"
    COMMODITY = "commodity"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TradeResult(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Instrument:
    """A tradable financial instrument.

    Attributes:
        symbol: Broker symbol string (e.g. ``XAUUSD``).
        name: Human-readable name.
        instrument_type: Category (forex, metal, etc.).
        base_currency: Base currency for pairs (None for metals).
        quote_currency: Quote currency for pairs (None for metals).
        point: Minimum price increment (broker-specific, verified later).
        min_lot: Minimum tradable lot size.
        max_lot: Maximum tradable lot size.
        lot_step: Lot size increment.
    """

    symbol: str
    name: str
    instrument_type: InstrumentType = InstrumentType.FOREX
    base_currency: Optional[str] = None
    quote_currency: Optional[str] = None
    point: Decimal = Decimal("0.00001")
    min_lot: Decimal = Decimal("0.01")
    max_lot: Decimal = Decimal("100.0")
    lot_step: Decimal = Decimal("0.01")


@dataclass(frozen=True)
class Tick:
    """A single price tick for an instrument."""

    symbol: str
    bid: Decimal
    ask: Decimal
    timestamp: datetime
    last: Optional[Decimal] = None
    volume: Optional[int] = None

    @property
    def spread(self) -> Decimal:
        """Bid-ask spread in price units."""
        return self.ask - self.bid

    @property
    def mid(self) -> Decimal:
        """Mid price."""
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class Candle:
    """A single OHLC candle."""

    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    timestamp: datetime
    volume: Optional[int] = None


@dataclass(frozen=True)
class OrderRequest:
    """A request to open a new order. Validated before submission to a broker."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    volume: Decimal
    price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    comment: Optional[str] = None
    magic_number: Optional[int] = None


@dataclass(frozen=True)
class Order:
    """An order as known by the broker (or mock broker)."""

    ticket: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    volume: Decimal
    status: OrderStatus
    price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    profit: Optional[Decimal] = None
    comment: Optional[str] = None
    magic_number: Optional[int] = None


@dataclass(frozen=True)
class Position:
    """An open position."""

    ticket: str
    symbol: str
    side: OrderSide
    volume: Decimal
    open_price: Decimal
    current_price: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    profit: Decimal = Decimal("0")
    open_time: Optional[datetime] = None
    comment: Optional[str] = None
    magic_number: Optional[int] = None


@dataclass(frozen=True)
class TradeResultModel:
    """Outcome of a trade execution attempt."""

    success: bool
    result: TradeResult
    ticket: Optional[str] = None
    symbol: Optional[str] = None
    volume: Optional[Decimal] = None
    price: Optional[Decimal] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    order: Optional[Order] = None


@dataclass(frozen=True)
class AccountInfo:
    """Broker account information (read-only snapshot)."""

    login: int
    name: str
    server: str
    currency: str
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Optional[Decimal] = None
    trade_allowed: bool = False
    trade_mode: str = "demo"  # demo | live
