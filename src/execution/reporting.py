"""Phase 9 execution reporting.

Readable status and execution reports. Never logs credentials or account
login identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.execution.account_identity import AccountIdentity
from src.execution.execution_journal import ExecutionJournal
from src.execution.models import ExecutionRecord, ExecutionState
from src.execution.trade_monitor import MonitorSnapshot


@dataclass
class ExecutionReport:
    generated_at: str
    mode: str
    summary: Dict[str, Any]
    executions: List[Dict[str, Any]]
    positions: List[Dict[str, Any]]
    orders: List[Dict[str, Any]]
    disclaimer: str


class ExecutionReporter:
    """Generates readable execution reports."""

    def __init__(self, journal: ExecutionJournal) -> None:
        self.journal = journal

    def report(self, snapshot: MonitorSnapshot, account_identity: Optional[AccountIdentity] = None) -> ExecutionReport:
        records = self.journal.load_all()
        executions = [self._record_summary(r) for r in records]
        summary = {
            "total_executions": len(records),
            "by_state": snapshot.execution_status.by_state,
            "unresolved": snapshot.execution_status.unresolved,
            "open_positions": len(snapshot.positions),
            "active_orders": len(snapshot.orders),
            "equity": str(snapshot.equity),
            "free_margin": str(snapshot.free_margin),
            "market_connected": snapshot.market.connected,
            "quote_fresh": snapshot.market.quote_fresh,
        }
        positions = [self._position_summary(p) for p in snapshot.positions]
        orders = [self._order_summary(o) for o in snapshot.orders]
        account_block = None
        if account_identity is not None:
            account_block = {
                "server": account_identity.server,
                "trade_mode": account_identity.trade_mode,
                "is_demo": account_identity.is_demo,
                "trade_allowed": account_identity.trade_allowed,
                "verified_at": account_identity.verified_at.isoformat() if account_identity.verified_at else None,
            }
        return ExecutionReport(
            generated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            mode="execution",
            summary={**summary, "account": account_block},
            executions=executions,
            positions=positions,
            orders=orders,
            disclaimer=(
                "Execution reports describe simulated/demo activity only. "
                "No real trading is performed. Results are not indicative of future performance."
            ),
        )

    def _record_summary(self, r: ExecutionRecord) -> Dict[str, Any]:
        return {
            "execution_id": r.execution_id,
            "signal_id": r.signal_id,
            "strategy": f"{r.strategy_name} v{r.strategy_version}",
            "symbol": r.symbol,
            "side": r.side,
            "volume": str(r.volume),
            "state": r.state.value,
            "mode": r.mode,
            "ticket": r.broker_order_ticket,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "reconciliation_status": r.reconciliation_status,
            "reason": r.reason,
        }

    @staticmethod
    def _position_summary(p) -> Dict[str, Any]:
        return {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "side": p.side.value,
            "volume": str(p.volume),
            "open_price": str(p.open_price),
            "current_price": str(p.current_price),
            "profit": str(p.profit),
            "magic_number": p.magic_number,
        }

    @staticmethod
    def _order_summary(o) -> Dict[str, Any]:
        return {
            "ticket": o.ticket,
            "symbol": o.symbol,
            "side": o.side.value,
            "volume": str(o.volume),
            "status": o.status.value,
            "price": str(o.price) if o.price else None,
            "magic_number": o.magic_number,
        }
