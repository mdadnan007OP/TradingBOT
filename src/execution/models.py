"""Phase 9 execution models.

Execution records describe simulated or demo trading activity only. They never
describe live/real trading. All monetary amounts use Decimal.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionState(str, Enum):
    """Explicit execution lifecycle states."""

    CREATED = "CREATED"
    PENDING_VALIDATION = "PENDING_VALIDATION"
    RISK_APPROVED = "RISK_APPROVED"
    AWAITING_MANUAL_APPROVAL = "AWAITING_MANUAL_APPROVAL"
    PRE_TRADE_CHECKED = "PRE_TRADE_CHECKED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"

    @property
    def is_terminal(self) -> bool:
        return self in (
            ExecutionState.FILLED,
            ExecutionState.REJECTED,
            ExecutionState.CANCELLED,
            ExecutionState.EXPIRED,
            ExecutionState.UNKNOWN,
            ExecutionState.RECONCILED,
        )


class OrderFillPolicy(str, Enum):
    """Broker-supported filling policies (normalized)."""

    FILL_OR_KILL = "FILL_OR_KILL"
    IMMEDIATE_OR_CANCEL = "IMMEDIATE_OR_CANCEL"
    RETURN = "RETURN"


class BrokerRetCode(str, Enum):
    """Official MT5 trade-server return codes."""

    DONE = "DONE"
    DONE_PARTIAL = "DONE_PARTIAL"
    PLACED = "PLACED"
    REQUOTE = "REQUOTE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    TIMEOUT = "TIMEOUT"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_VOLUME = "INVALID_VOLUME"
    INVALID_STOPS = "INVALID_STOPS"
    MARKET_CLOSED = "MARKET_CLOSED"
    NO_MONEY = "NO_MONEY"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExecutionRequest:
    """A proposed execution (signal + risk decision + broker intent)."""

    execution_id: str
    signal_id: str
    strategy_name: str
    strategy_version: str
    symbol: str
    side: str  # "LONG"/"SHORT" (aligned with Phase 5 SignalDirection)
    volume: Decimal
    entry_reference_price: Decimal
    stop_loss_price: Optional[Decimal]
    take_profit_price: Optional[Decimal]
    risk_decision_id: str
    monetary_risk: Decimal
    risk_percent: Decimal
    fill_policy: OrderFillPolicy
    deviation_points: int
    magic_number: int
    comment: str
    execution_mode: str  # ExecutionMode value
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", _utc(self.created_at))


@dataclass(frozen=True)
class ExecutionRecord:
    """Durable audit record of a single execution attempt."""

    execution_id: str
    signal_id: str
    strategy_name: str
    strategy_version: str
    symbol: str
    side: str
    volume: Decimal
    entry_price: Optional[Decimal]
    stop_loss_price: Optional[Decimal]
    take_profit_price: Optional[Decimal]
    state: ExecutionState
    mode: str
    magic_number: int
    comment: str
    created_at: datetime
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    broker_order_ticket: Optional[str] = None
    broker_deal_ticket: Optional[str] = None
    broker_request_id: Optional[str] = None
    filled_volume: Optional[Decimal] = None
    filled_price: Optional[Decimal] = None
    remaining_volume: Optional[Decimal] = None
    broker_retcode: Optional[str] = None
    broker_external_code: Optional[str] = None
    broker_comment: Optional[str] = None
    execution_timestamp: Optional[datetime] = None
    request_fingerprint: str = ""
    authorization_token: Optional[str] = None
    reconciliation_status: str = "unreconciled"
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", _utc(self.created_at))
        if self.submitted_at is not None:
            object.__setattr__(self, "submitted_at", _utc(self.submitted_at))
        if self.filled_at is not None:
            object.__setattr__(self, "filled_at", _utc(self.filled_at))
        if self.execution_timestamp is not None:
            object.__setattr__(self, "execution_timestamp", _utc(self.execution_timestamp))

    @property
    def is_terminal(self) -> bool:
        return self.state.is_terminal


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of an execution attempt (never a live trade)."""

    execution_id: str
    success: bool
    state: ExecutionState
    ticket: Optional[str] = None
    symbol: Optional[str] = None
    volume: Optional[Decimal] = None
    price: Optional[Decimal] = None
    filled_volume: Optional[Decimal] = None
    filled_price: Optional[Decimal] = None
    remaining_volume: Optional[Decimal] = None
    broker_retcode: Optional[str] = None
    broker_comment: Optional[str] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    reconciled: bool = False
    retry_permitted: bool = False


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_fingerprint(
    *,
    signal_id: str,
    symbol: str,
    side: str,
    volume: Decimal,
    entry_price: Decimal,
    stop_loss_price: Optional[Decimal],
    take_profit_price: Optional[Decimal],
    magic_number: int,
    mode: str,
) -> str:
    """Stable fingerprint for idempotency (bound to exact order parameters)."""
    payload = "|".join(
        [
            signal_id,
            symbol,
            side,
            str(volume),
            str(entry_price),
            str(stop_loss_price or ""),
            str(take_profit_price or ""),
            str(magic_number),
            mode,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def new_execution_id() -> str:
    return f"exec-{uuid.uuid4().hex[:16]}"


def new_authorization_token() -> str:
    return f"auth-{uuid.uuid4().hex[:16]}"
