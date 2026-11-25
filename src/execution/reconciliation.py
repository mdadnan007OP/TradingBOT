"""Phase 9 order and position reconciliation.

Reconciles broker-reported orders/positions/deals against the local execution
journal. Uncertain executions (timeout/unknown) are resolved here — never by
blind retry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.execution.account_identity import AccountIdentity
from src.execution.execution_journal import ExecutionJournal
from src.execution.interfaces import ExecutionGateway
from src.execution.models import (
    ExecutionRecord,
    ExecutionState,
    BrokerRetCode,
)


@dataclass(frozen=True)
class ReconciliationResult:
    execution_id: str
    journal_state: ExecutionState
    broker_state: Optional[str]
    reconciled: bool
    discrepancy: Optional[str]
    action: str  # "none", "mark_filled", "mark_rejected", "manual_review"
    details: Dict[str, Any] = field(default_factory=dict)


class Reconciliation:
    """Reconciles broker state with local execution journal."""

    def __init__(self, gateway: ExecutionGateway, journal: ExecutionJournal) -> None:
        self.gateway = gateway
        self.journal = journal

    def reconcile_all(self, account_identity: Optional[AccountIdentity] = None) -> List[ReconciliationResult]:
        results: List[ReconciliationResult] = []
        records = self.journal.load_all()
        broker_orders = self._fetch_orders()
        broker_positions = self._fetch_positions()
        broker_deals = self._fetch_deals()

        order_index = {o.ticket: o for o in broker_orders}
        position_index = {p.ticket: p for p in broker_positions}
        deal_index: Dict[str, Any] = {}
        for d in broker_deals:
            deal_index[str(d.get("order", ""))] = d

        for record in records:
            if record.state.is_terminal and record.reconciliation_status == "reconciled":
                continue
            result = self._reconcile_one(
                record, order_index, position_index, deal_index, account_identity
            )
            results.append(result)
        return results

    def _reconcile_one(
        self,
        record: ExecutionRecord,
        order_index: Dict[str, Any],
        position_index: Dict[str, Any],
        deal_index: Dict[str, Any],
        account_identity: Optional[AccountIdentity],
    ) -> ReconciliationResult:
        ticket = record.broker_order_ticket
        discrepancy: Optional[str] = None
        action = "none"
        broker_state: Optional[str] = None

        if ticket is None:
            # No broker ticket: never submitted or submission failed.
            if record.state in (ExecutionState.SUBMITTED, ExecutionState.UNKNOWN):
                discrepancy = "Submitted but no broker ticket; state unknown"
                action = "manual_review"
                broker_state = "unknown"
            return ReconciliationResult(
                execution_id=record.execution_id,
                journal_state=record.state,
                broker_state=broker_state,
                reconciled=False,
                discrepancy=discrepancy,
                action=action,
                details={"reason": record.reason},
            )

        order = order_index.get(ticket)
        position = position_index.get(ticket)
        deal = deal_index.get(ticket)

        if order is None and position is None and deal is None:
            discrepancy = f"Ticket {ticket} not found in broker orders/positions/deals"
            if record.state == ExecutionState.FILLED:
                discrepancy += " (journal says FILLED but broker has no record)"
                action = "manual_review"
            elif record.state == ExecutionState.UNKNOWN:
                action = "manual_review"
            broker_state = "not_found"
            return ReconciliationResult(
                execution_id=record.execution_id,
                journal_state=record.state,
                broker_state=broker_state,
                reconciled=False,
                discrepancy=discrepancy,
                action=action,
            )

        # Determine broker state.
        if deal is not None:
            broker_state = "filled"
            if record.state != ExecutionState.FILLED:
                action = "mark_filled"
                discrepancy = "Broker deal exists; journal not FILLED"
        elif position is not None:
            broker_state = "open"
            if record.state == ExecutionState.UNKNOWN:
                action = "mark_filled"
                discrepancy = "Position exists; submission was successful"
        elif order is not None:
            broker_state = order.status.value
            if record.state == ExecutionState.UNKNOWN:
                action = "manual_review"
                discrepancy = "Order exists but fill status unclear"

        reconciled = (
            record.reconciliation_status == "reconciled"
            and (discrepancy is None or action == "none")
        )
        return ReconciliationResult(
            execution_id=record.execution_id,
            journal_state=record.state,
            broker_state=broker_state,
            reconciled=reconciled,
            discrepancy=discrepancy,
            action=action,
            details={
                "ticket": ticket,
                "has_order": order is not None,
                "has_position": position is not None,
                "has_deal": deal is not None,
            },
        )

    def apply_reconciliation(self, result: ReconciliationResult) -> None:
        """Mark a record as reconciled if action resolved."""
        from dataclasses import replace

        record = self.journal.get(result.execution_id)
        if record is None:
            return
        if result.action in ("mark_filled", "mark_rejected"):
            new_state = (
                ExecutionState.FILLED if result.action == "mark_filled" else ExecutionState.REJECTED
            )
            updated = replace(
                record,
                state=new_state,
                reconciliation_status="reconciled",
            )
            self.journal.append(updated)
        elif result.action == "none":
            updated = replace(record, reconciliation_status="reconciled")
            self.journal.append(updated)
        # manual_review: leave unreconciled for explicit user action.

    # ------------------------------------------------------------------
    # Broker fetches (demo adapter only)
    # ------------------------------------------------------------------

    def _fetch_orders(self) -> List[Any]:
        if self.gateway.is_connected():
            try:
                return self.gateway.get_orders()
            except Exception:  # noqa: BLE001
                return []
        return []

    def _fetch_positions(self) -> List[Any]:
        if self.gateway.is_connected():
            try:
                return self.gateway.get_positions()
            except Exception:  # noqa: BLE001
                return []
        return []

    def _fetch_deals(self) -> List[Dict[str, Any]]:
        if self.gateway.is_connected():
            try:
                return self.gateway.get_history_deals()
            except Exception:  # noqa: BLE001
                return []
        return []
