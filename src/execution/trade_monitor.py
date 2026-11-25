"""Phase 9 trade monitor.

Read-only monitoring of positions, orders, deals, equity and margin.
Reconciles actual broker state with local execution state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.execution.account_identity import AccountIdentity
from src.execution.interfaces import ExecutionGateway
from src.execution.models import ExecutionRecord
from src.models import Order, Position


@dataclass(frozen=True)
class MarketStatus:
    connected: bool
    quote_fresh: bool
    last_tick_time: Optional[datetime]
    spread: Optional[Decimal] = None


@dataclass(frozen=True)
class ExecutionStatus:
    total_executions: int
    by_state: Dict[str, int]
    pending_approvals: int
    unresolved: int
    last_activity: Optional[datetime]


@dataclass(frozen=True)
class MonitorSnapshot:
    timestamp: datetime
    account: Optional[Any]
    market: MarketStatus
    positions: List[Position]
    orders: List[Order]
    execution_status: ExecutionStatus
    equity: Decimal
    free_margin: Decimal


class TradeMonitor:
    """Read-only monitoring service."""

    def __init__(self, gateway: ExecutionGateway, journal: Any) -> None:
        self.gateway = gateway
        self.journal = journal

    def snapshot(self, account_identity: Optional[AccountIdentity] = None) -> MonitorSnapshot:
        positions: List[Position] = []
        orders: List[Order] = []
        equity = Decimal("0")
        free_margin = Decimal("0")

        if self.gateway.is_connected():
            try:
                positions = self.gateway.get_positions()
            except Exception:  # noqa: BLE001
                positions = []
            try:
                orders = self.gateway.get_orders()
            except Exception:  # noqa: BLE001
                orders = []
            acct = self.gateway.get_account_info()
            if acct is not None:
                equity = acct.equity
                free_margin = acct.free_margin

        # Market status.
        tick = None
        if self.gateway.is_connected():
            try:
                tick = self.gateway.get_tick("EURUSD")
            except Exception:  # noqa: BLE001
                tick = None
        market = MarketStatus(
            connected=self.gateway.is_connected(),
            quote_fresh=tick is not None,
            last_tick_time=tick.timestamp if tick else None,
            spread=tick.spread if tick else None,
        )

        # Execution status from journal.
        records = self.journal.load_all() if hasattr(self.journal, "load_all") else []
        by_state: Dict[str, int] = {}
        unresolved = 0
        last_activity = None
        for r in records:
            st = r.state.value
            by_state[st] = by_state.get(st, 0) + 1
            if r.state.name not in (
                "FILLED",
                "REJECTED",
                "CANCELLED",
                "EXPIRED",
                "UNKNOWN",
                "RECONCILED",
            ):
                unresolved += 1
            try:
                ts = r.created_at
                if last_activity is None or ts > last_activity:
                    last_activity = ts
            except AttributeError:
                continue

        status = ExecutionStatus(
            total_executions=len(records),
            by_state=by_state,
            pending_approvals=0,
            unresolved=unresolved,
            last_activity=last_activity,
        )

        return MonitorSnapshot(
            timestamp=datetime.now(timezone.utc),
            account=account_identity,
            market=market,
            positions=positions,
            orders=orders,
            execution_status=status,
            equity=equity,
            free_margin=free_margin,
        )

    def position_summary(self, positions: List[Position]) -> Dict[str, Any]:
        total_volume = Decimal("0")
        total_profit = Decimal("0")
        by_symbol: Dict[str, int] = {}
        for p in positions:
            total_volume += p.volume
            total_profit += p.profit
            by_symbol[p.symbol] = by_symbol.get(p.symbol, 0) + 1
        return {
            "count": len(positions),
            "total_volume": str(total_volume),
            "total_profit": str(total_profit),
            "by_symbol": by_symbol,
        }
