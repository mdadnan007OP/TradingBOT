"""Backtesting data models.

Phase 8 is a historical simulation phase. It simulates trading activity against
historical market data and NEVER places real or demo broker orders. All objects
here describe *simulated* state only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class OrderSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    PENDING = "PENDING"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    MANUAL = "MANUAL"
    END_OF_DATA = "END_OF_DATA"
    SIGNAL = "SIGNAL"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class SimulatedOrder:
    """A simulated order. Never sent to a broker."""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    volume: Decimal
    requested_price: Optional[Decimal] = None
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    fill_price: Optional[Decimal] = None
    strategy_name: str = ""
    signal_id: str = ""
    reject_reason: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", _utc(self.created_at))
        object.__setattr__(self, "filled_at", _utc(self.filled_at))


@dataclass
class SimulatedPosition:
    """An open or closed simulated position."""

    position_id: str
    symbol: str
    side: OrderSide
    volume: Decimal
    entry_price: Decimal
    entry_time: datetime
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    strategy_name: str = ""
    signal_id: str = ""
    status: PositionStatus = PositionStatus.OPEN
    exit_price: Optional[Decimal] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[ExitReason] = None
    commission: Decimal = Decimal("0")
    swap: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    ambiguous_exit: bool = False
    partial_closes: List[Dict[str, Any]] = field(default_factory=list)
    remaining_volume: Optional[Decimal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_time", _utc(self.entry_time))
        object.__setattr__(self, "exit_time", _utc(self.exit_time))
        if self.remaining_volume is None:
            object.__setattr__(self, "remaining_volume", self.volume)

    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPEN

    def gross_pnl(self) -> Optional[Decimal]:
        """Price-only PnL (before costs) in quote/profit currency.

        Returns None if the position is not closed.
        """
        if self.exit_price is None:
            return None
        diff = self.exit_price - self.entry_price
        if self.side == OrderSide.SHORT:
            diff = -diff
        return diff * self.volume

    def net_pnl(self) -> Optional[Decimal]:
        """Net PnL after commission, swap, slippage (in profit currency)."""
        gross = self.gross_pnl()
        if gross is None:
            return None
        return gross - self.commission - self.swap - self.slippage


@dataclass
class ClosedTrade:
    """A closed simulated trade with realized PnL (account currency)."""

    trade_id: str
    position_id: str
    symbol: str
    side: OrderSide
    volume: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_time: datetime
    exit_time: datetime
    exit_reason: ExitReason
    strategy_name: str
    gross_pnl_quote: Decimal
    net_pnl_account: Decimal
    commission: Decimal = Decimal("0")
    swap: Decimal = Decimal("0")
    slippage_quote: Decimal = Decimal("0")
    ambiguous_exit: bool = False
    r_multiple: Optional[Decimal] = None
    holding_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_time", _utc(self.entry_time))
        object.__setattr__(self, "exit_time", _utc(self.exit_time))
        if self.holding_seconds is None and self.entry_time and self.exit_time:
            object.__setattr__(
                self, "holding_seconds",
                (self.exit_time - self.entry_time).total_seconds(),
            )

    @property
    def is_win(self) -> bool:
        return self.net_pnl_account > 0

    @property
    def is_loss(self) -> bool:
        return self.net_pnl_account < 0

    @property
    def is_breakeven(self) -> bool:
        return self.net_pnl_account == 0


@dataclass
class EquityPoint:
    """A single point on the equity/balance curve."""

    timestamp: datetime
    equity: Decimal
    balance: Decimal
    margin: Decimal = Decimal("0")
    free_margin: Optional[Decimal] = None
    open_positions: int = 0
    drawdown_percent: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", _utc(self.timestamp))


class EventType(str, Enum):
    BAR = "BAR"
    SIGNAL = "SIGNAL"
    RISK_DECISION = "RISK_DECISION"
    ORDER = "ORDER"
    FILL = "FILL"
    EXIT = "EXIT"
    NEWS_BLOCK = "NEWS_BLOCK"
    REJECTION = "REJECTION"


@dataclass
class BacktestEvent:
    """A single recorded event in the backtest timeline."""

    event_type: EventType
    timestamp: datetime
    symbol: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", _utc(self.timestamp))


@dataclass
class BacktestResult:
    """Complete result of a backtest run."""

    config_name: str
    symbols: List[str]
    timeframes: List[str]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    equity_curve: List[EquityPoint] = field(default_factory=list)
    trades: List[ClosedTrade] = field(default_factory=list)
    events: List[BacktestEvent] = field(default_factory=list)
    rejected_signals: List[Dict[str, Any]] = field(default_factory=list)
    news_blocks: List[Dict[str, Any]] = field(default_factory=list)
    risk_lockouts: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def final_equity(self) -> Optional[Decimal]:
        return self.equity_curve[-1].equity if self.equity_curve else None

    @property
    def final_balance(self) -> Optional[Decimal]:
        return self.equity_curve[-1].balance if self.equity_curve else None